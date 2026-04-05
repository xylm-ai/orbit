import secrets
import io
import base64
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pyotp

from app.database import get_db
from app.models import Family, User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, TOTPSetupResponse, TOTPVerifyRequest
from app.services.auth import hash_password, verify_password, create_access_token
from app.deps import current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    slug = secrets.token_urlsafe(8).lower()
    family = Family(name=body.family_name, inbound_email_slug=slug)
    db.add(family)
    await db.flush()

    user = User(
        family_id=family.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=UserRole.owner,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.family_id, user.role.value)
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.two_fa_enabled:
        if not body.totp_code:
            raise HTTPException(status_code=401, detail="2FA code required")
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(body.totp_code, valid_window=1):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    token = create_access_token(user.id, user.family_id, user.role.value)
    return TokenResponse(access_token=token)

@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.two_fa_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = pyotp.random_base32()
    user.totp_secret = secret
    await db.commit()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="ORBIT")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return TOTPSetupResponse(secret=secret, qr_uri=f"data:image/png;base64,{qr_b64}")

@router.post("/2fa/verify", status_code=204)
async def verify_2fa(
    body: TOTPVerifyRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Run /auth/2fa/setup first")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    user.two_fa_enabled = True
    await db.commit()
