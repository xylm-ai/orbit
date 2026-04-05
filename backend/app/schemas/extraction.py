import uuid
from typing import Any
from pydantic import BaseModel
from app.models.extraction import ReviewStatus


class ExtractionReviewResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    extracted_data: list[dict[str, Any]]
    review_status: ReviewStatus

    model_config = {"from_attributes": True}


class RowEditRequest(BaseModel):
    date: str | None = None
    isin: str | None = None
    security_name: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    scheme_code: str | None = None
    scheme_name: str | None = None
    units: float | None = None
    nav: float | None = None
    narration: str | None = None


class ConfirmResponse(BaseModel):
    events_written: int
    skipped_duplicates: int


class RejectRequest(BaseModel):
    reason: str = ""
