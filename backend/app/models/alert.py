import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AlertType(str, enum.Enum):
    price_drop = "price_drop"
    price_drop_critical = "price_drop_critical"
    concentration = "concentration"
    drawdown = "drawdown"
    reconciliation_flag = "reconciliation_flag"


class Severity(str, enum.Enum):
    warning = "warning"
    critical = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=True, index=True
    )
    identifier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    alert_type: Mapped[AlertType] = mapped_column(SAEnum(AlertType), nullable=False)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
