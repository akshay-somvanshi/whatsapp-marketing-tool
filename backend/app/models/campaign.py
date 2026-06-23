import enum
import uuid

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.database import Base


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    running = "running"
    completed = "completed"
    failed = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    template_name = Column(Text, nullable=False)
    template_params = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'"),
    )
    audience_tags = Column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'"),
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        Enum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.draft,
    )
    sent_count = Column(Integer, nullable=False, default=0)
    delivered_count = Column(Integer, nullable=False, default=0)
    read_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
