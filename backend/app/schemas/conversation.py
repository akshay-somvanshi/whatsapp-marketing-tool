import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, computed_field

from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection, MessageStatus


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_phone: str
    direction: MessageDirection
    body: str
    status: MessageStatus
    wa_message_id: str | None
    template_name: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_phone: str
    status: ConversationStatus
    ai_enabled: bool
    session_expires_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def session_status(self) -> str:
        exp = self.session_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return "active" if exp > datetime.now(timezone.utc) else "expired"


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPatch(BaseModel):
    ai_enabled: bool


class SendMessageRequest(BaseModel):
    text: str
