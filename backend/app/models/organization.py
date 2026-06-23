import uuid

from sqlalchemy import Column, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Organization(Base):
    """A tenant. Owns all contacts/campaigns/conversations/messages and its own
    WhatsApp + AI channel credentials.

    NOTE: secret columns are plaintext in Phase 1. Encryption-at-rest is a
    tracked follow-up (see IMPROVEMENT_PLAN.md).
    """

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)

    # WhatsApp channel config
    whatsapp_phone_number_id = Column(Text, unique=True, nullable=True)
    whatsapp_api_token = Column(Text, nullable=True)
    whatsapp_business_account_id = Column(Text, nullable=True)

    # AI config
    ai_provider = Column(Text, nullable=False, default="anthropic")
    anthropic_api_key = Column(Text, nullable=True)
    gemini_api_key = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
