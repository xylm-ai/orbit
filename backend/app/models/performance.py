import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), unique=True, nullable=False, index=True
    )
    xirr: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    cagr: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    total_invested: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    abs_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
