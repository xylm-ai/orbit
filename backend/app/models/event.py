import uuid
import enum
from datetime import date, datetime
from sqlalchemy import ForeignKey, DateTime, Date, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base

class EventType(str, enum.Enum):
    opening_balance_set = "OpeningBalanceSet"
    security_bought = "SecurityBought"
    security_sold = "SecuritySold"
    dividend_received = "DividendReceived"
    mf_units_purchased = "MFUnitsPurchased"
    mf_units_redeemed = "MFUnitsRedeemed"
    bank_entry_recorded = "BankEntryRecorded"
    reconciliation_flagged = "ReconciliationFlagged"

class PortfolioEvent(Base):
    __tablename__ = "portfolio_events"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "version", name="uq_portfolio_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="events")
