import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class UserRole(str, enum.Enum):
    owner = "owner"
    advisor = "advisor"
    ca = "ca"
    viewer = "viewer"

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("families.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.viewer)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship("Family", back_populates="users")
    entity_access: Mapped[list["FamilyUserAccess"]] = relationship("FamilyUserAccess", back_populates="user")
