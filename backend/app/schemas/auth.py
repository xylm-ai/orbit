from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    family_name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TOTPSetupResponse(BaseModel):
    secret: str
    qr_uri: str

class TOTPVerifyRequest(BaseModel):
    totp_code: str
