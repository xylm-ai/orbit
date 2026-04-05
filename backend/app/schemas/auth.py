from pydantic import BaseModel, EmailStr, field_validator

class RegisterRequest(BaseModel):
    family_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

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
