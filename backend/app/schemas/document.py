import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.document import DocumentSource, DocType, DocumentStatus


class DocumentResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    portfolio_id: uuid.UUID | None
    source: DocumentSource
    doc_type: DocType | None
    status: DocumentStatus
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: uuid.UUID
    source: DocumentSource
    doc_type: DocType | None
    status: DocumentStatus
    uploaded_at: datetime
    failure_reason: str | None

    model_config = {"from_attributes": True}
