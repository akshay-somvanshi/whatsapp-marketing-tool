import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        # Natural key within a tenant; also the target of the composite FKs
        # from conversations/messages.
        UniqueConstraint("organization_id", "phone", name="uq_contact_org_phone"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    phone = Column(String(50), nullable=False)
    opted_in = Column(Boolean, nullable=False, default=False)
    opted_in_at = Column(DateTime(timezone=True), nullable=True)
    tags = Column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'"),
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
