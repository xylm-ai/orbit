import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, String, Numeric, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "identifier", name="uq_holding_portfolio_identifier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False, index=True
    )
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)   # ISIN or scheme_code
    security_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)  # equity | mf
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    avg_cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    dividend_income: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
