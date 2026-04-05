import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, String, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AllocationSnapshot(Base):
    __tablename__ = "allocation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True
    )
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)
    security_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
