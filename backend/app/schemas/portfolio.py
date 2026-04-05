from pydantic import BaseModel
from app.models.portfolio import PortfolioType
import uuid
from datetime import date, datetime

class PortfolioCreate(BaseModel):
    type: PortfolioType
    provider_name: str
    account_number: str | None = None
    opened_on: date | None = None

class PortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    entity_id: uuid.UUID
    type: PortfolioType
    provider_name: str
    account_number: str | None
    opened_on: date | None
    created_at: datetime
