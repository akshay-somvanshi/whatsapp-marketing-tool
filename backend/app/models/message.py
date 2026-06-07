import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_phone = Column(
        String(50),
        ForeignKey("contacts.phone", ondelete="CASCADE"),
        nullable=False,
    )
    direction = Column(
        Enum(MessageDirection, name="message_direction"), nullable=False
    )
    body = Column(Text, nullable=False)
    template_name = Column(Text, nullable=True)
    status = Column(
        Enum(MessageStatus, name="message_status"),
        nullable=False,
        default=MessageStatus.sent,
    )
    wa_message_id = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
