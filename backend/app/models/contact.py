import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    phone = Column(String(50), unique=True, nullable=False)
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
