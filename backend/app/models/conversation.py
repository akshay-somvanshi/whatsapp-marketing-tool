import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ConversationStatus(str, enum.Enum):
    active = "active"
    expired = "expired"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_phone = Column(
        String(50),
        ForeignKey("contacts.phone", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    session_expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        Enum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.active,
    )
    ai_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
