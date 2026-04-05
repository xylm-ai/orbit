from pydantic import BaseModel, EmailStr
from app.models.user import UserRole
import uuid

class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole

class AccessResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    user_id: uuid.UUID
    entity_id: uuid.UUID
    role: UserRole
