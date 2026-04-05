from pydantic import BaseModel
from app.models.entity import EntityType
import uuid
from datetime import datetime

class EntityCreate(BaseModel):
    name: str
    type: EntityType
    pan: str | None = None

class EntityResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    type: EntityType
    pan: str | None
    created_at: datetime
