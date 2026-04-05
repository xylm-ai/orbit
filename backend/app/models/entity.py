import uuid
import enum
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class EntityType(str, enum.Enum):
    individual = "individual"
    huf = "huf"
    company = "company"
    trust = "trust"

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("families.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[EntityType] = mapped_column(SAEnum(EntityType), nullable=False)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship("Family", back_populates="entities")
    portfolios: Mapped[list["Portfolio"]] = relationship("Portfolio", back_populates="entity")
    user_access: Mapped[list["FamilyUserAccess"]] = relationship("FamilyUserAccess", back_populates="entity")
