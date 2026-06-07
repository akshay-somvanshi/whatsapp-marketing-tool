import asyncio
import logging
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from celery import Celery

from app.ai.handler import generate_reply
from app.config import settings
from app.database import async_session_factory
from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.whatsapp.client import wa_client

logger = logging.getLogger(__name__)

celery_app = Celery(
    "wa_marketing",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="tasks.process_inbound_message")
def process_inbound_message(payload: dict) -> None:
    """Celery task entry-point — synchronous wrapper around the async pipeline."""
    asyncio.run(_process_inbound_message_async(payload))


async def _process_inbound_message_async(payload: dict) -> None:
    """
    Full inbound message pipeline.

    Called directly in tests (bypassing Celery) to avoid asyncio.run()
    being invoked inside a running event loop.
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError):
        logger.warning("Malformed webhook payload — skipping")
        return

    async with async_session_factory() as session:
        for status_update in value.get("statuses", []):
            await _handle_status_update(session, status_update)
        for msg_data in value.get("messages", []):
            await _handle_inbound_message(session, msg_data)
        await session.commit()


async def _handle_status_update(session, status_update: dict) -> None:
    wa_msg_id = status_update.get("id")
    raw_status = status_update.get("status")
    if not wa_msg_id or not raw_status:
        return
    try:
        new_status = MessageStatus(raw_status)
    except ValueError:
        logger.warning("Unknown status value: %s", raw_status)
        return
    result = await session.execute(
        sa.select(Message).where(Message.wa_message_id == wa_msg_id)
    )
    msg = result.scalar_one_or_none()
    if msg:
        msg.status = new_status


async def _handle_inbound_message(session, msg_data: dict) -> None:
    raw_phone = msg_data.get("from", "")
    phone = f"+{raw_phone}" if not raw_phone.startswith("+") else raw_phone
    wa_msg_id = msg_data.get("id") or None
    body = msg_data.get("text", {}).get("body", "")

    if not phone or not body:
        return

    # 1. Upsert contact
    result = await session.execute(sa.select(Contact).where(Contact.phone == phone))
    contact = result.scalar_one_or_none()
    if contact is None:
        contact = Contact(name=phone, phone=phone, opted_in=False)
        session.add(contact)
        await session.flush()

    # 2. Save inbound message
    inbound = Message(
        contact_phone=phone,
        direction=MessageDirection.inbound,
        body=body,
        status=MessageStatus.sent,
        wa_message_id=wa_msg_id,
    )
    session.add(inbound)
    await session.flush()

    # 3. Mark as read — best effort, never block the pipeline
    if wa_msg_id:
        try:
            await wa_client.mark_as_read(wa_msg_id)
        except Exception as exc:
            logger.warning("mark_as_read failed for %s: %s", wa_msg_id, exc)

    # 4. Upsert conversation — reset 24-hour session window
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    result = await session.execute(
        sa.select(Conversation).where(Conversation.contact_phone == phone)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            contact_phone=phone,
            session_expires_at=expires_at,
            status=ConversationStatus.active,
        )
        session.add(conversation)
    else:
        conversation.session_expires_at = expires_at
        conversation.status = ConversationStatus.active
    await session.flush()

    # 5. STOP opt-out
    if body.strip().upper() == "STOP":
        contact.opted_in = False
        logger.info("Contact %s opted out via STOP", phone)
        return

    # 6. AI auto-reply when enabled for this conversation
    if conversation.ai_enabled:
        await _send_ai_reply(session, contact, conversation)


async def _send_ai_reply(session, contact, conversation) -> None:
    try:
        result = await session.execute(
            sa.select(Message)
            .where(Message.contact_phone == contact.phone)
            .order_by(Message.created_at.asc())
            .limit(settings.AI_HISTORY_LIMIT)
        )
        history = result.scalars().all()

        messages_for_ai = [
            {
                "role": "user" if m.direction == MessageDirection.inbound else "assistant",
                "content": m.body,
            }
            for m in history
        ]

        action_result = await generate_reply(
            messages=messages_for_ai,
            contact_name=contact.name,
        )
        action = action_result.get("action", "reply")

        if action == "reply":
            reply_text = action_result.get("text", "")
            if reply_text:
                sent_id = await wa_client.send_text_message(contact.phone, reply_text)
                session.add(
                    Message(
                        contact_phone=contact.phone,
                        direction=MessageDirection.outbound,
                        body=reply_text,
                        status=MessageStatus.sent,
                        wa_message_id=sent_id,
                    )
                )

        elif action == "escalate":
            conversation.ai_enabled = False
            logger.info("Escalated conversation for %s", contact.phone)

    except Exception:
        logger.exception("AI handler failed for contact %s", contact.phone)
