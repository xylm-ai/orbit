import uuid
import enum
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base


class DocumentSource(str, enum.Enum):
    email = "email"
    upload = "upload"


class DocType(str, enum.Enum):
    contract_note = "contract_note"
    pms_transaction = "pms_transaction"
    cas = "cas"
    bank_statement = "bank_statement"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    classifying = "classifying"
    preprocessing = "preprocessing"
    extracting = "extracting"
    normalizing = "normalizing"
    awaiting_review = "awaiting_review"
    ingested = "ingested"
    failed = "failed"
    rejected_sender = "rejected_sender"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=True)
    source: Mapped[DocumentSource] = mapped_column(SAEnum(DocumentSource), nullable=False)
    doc_type: Mapped[DocType | None] = mapped_column(SAEnum(DocType), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preprocessed_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(SAEnum(DocumentStatus), nullable=False, default=DocumentStatus.pending)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extraction: Mapped["StagedExtraction | None"] = relationship("StagedExtraction", back_populates="document", uselist=False)
