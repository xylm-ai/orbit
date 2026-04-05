import uuid
import enum
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class PortfolioType(str, enum.Enum):
    pms = "pms"
    equity = "equity"
    mf = "mf"

class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    type: Mapped[PortfolioType] = mapped_column(SAEnum(PortfolioType), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entity: Mapped["Entity"] = relationship("Entity", back_populates="portfolios")
    events: Mapped[list["PortfolioEvent"]] = relationship("PortfolioEvent", back_populates="portfolio")
