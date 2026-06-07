import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from celery import Celery

from app.ai.handler import generate_reply
from app.config import settings
from app.database import async_session_factory
from app.models.campaign import Campaign, CampaignStatus
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

celery_app.conf.beat_schedule = {
    "check-session-expiry": {
        "task": "tasks.check_session_expiry",
        "schedule": 3600.0,  # every hour
    },
    "trigger-post-purchase": {
        "task": "tasks.trigger_post_purchase",
        "schedule": 3600.0,  # every hour
    },
}


# ─── Phase 4: Inbound message processing ─────────────────────────────────────


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

        elif action == "save_review":
            review_text = action_result.get("review", "")
            reply_text = action_result.get("text", "")
            logger.info("Review from %s: %s", contact.phone, review_text)
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

    except Exception:
        logger.exception("AI handler failed for contact %s", contact.phone)


# ─── Phase 6: Campaign fanout ─────────────────────────────────────────────────


@celery_app.task(name="tasks.send_campaign_task")
def send_campaign_task(campaign_id: str) -> None:
    asyncio.run(_send_campaign_async(campaign_id))


async def _send_campaign_async(campaign_id: str) -> None:
    """
    Fan-out a campaign to all matching opted-in contacts.
    Called directly in tests to avoid nested asyncio.run() issues.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            sa.select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            logger.error("Campaign %s not found", campaign_id)
            return

        campaign.status = CampaignStatus.running
        await session.flush()

        # Find opted-in contacts matching audience tags
        stmt = sa.select(Contact).where(Contact.opted_in.is_(True))
        if campaign.audience_tags:
            stmt = stmt.where(
                sa.or_(
                    *(sa.literal(tag) == sa.func.any(Contact.tags) for tag in campaign.audience_tags)
                )
            )
        contacts = (await session.execute(stmt)).scalars().all()

        sent = 0
        for contact in contacts:
            try:
                wa_msg_id = await wa_client.send_template_message(
                    phone=contact.phone,
                    template_name=campaign.template_name,
                    language_code="en",
                    components=[],
                )
                session.add(
                    Message(
                        contact_phone=contact.phone,
                        direction=MessageDirection.outbound,
                        body=f"[{campaign.template_name}]",
                        status=MessageStatus.sent,
                        wa_message_id=wa_msg_id,
                        template_name=campaign.template_name,
                    )
                )
                sent += 1
            except Exception as exc:
                logger.warning("Failed to send campaign msg to %s: %s", contact.phone, exc)

        campaign.sent_count = sent
        campaign.status = CampaignStatus.completed
        await session.commit()


# ─── Phase 6: Beat tasks ──────────────────────────────────────────────────────


@celery_app.task(name="tasks.check_session_expiry")
def check_session_expiry_task() -> None:
    asyncio.run(_check_session_expiry_async())


async def _check_session_expiry_async() -> None:
    """Mark conversations whose 24-hour session window has elapsed as expired."""
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)
        await session.execute(
            sa.update(Conversation)
            .where(
                Conversation.session_expires_at < now,
                Conversation.status == ConversationStatus.active,
            )
            .values(status=ConversationStatus.expired)
        )
        await session.commit()


@celery_app.task(name="tasks.trigger_post_purchase")
def trigger_post_purchase_task() -> None:
    asyncio.run(_trigger_post_purchase_async())


async def _trigger_post_purchase_async() -> None:
    """
    Send the review_request template to contacts tagged 'purchased' in the
    last 72 hours who have not yet received it.  Idempotent: checks for an
    existing outbound review_request message before sending.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)

    async with async_session_factory() as session:
        contacts = (
            await session.execute(
                sa.select(Contact).where(
                    sa.literal("purchased") == sa.func.any(Contact.tags),
                    Contact.opted_in.is_(True),
                    Contact.created_at >= cutoff,
                )
            )
        ).scalars().all()

        for contact in contacts:
            already_sent = (
                await session.execute(
                    sa.select(Message).where(
                        Message.contact_phone == contact.phone,
                        Message.template_name == "review_request",
                        Message.direction == MessageDirection.outbound,
                    )
                )
            ).scalar_one_or_none()

            if already_sent is not None:
                continue

            try:
                wa_msg_id = await wa_client.send_template_message(
                    phone=contact.phone,
                    template_name="review_request",
                    language_code="en",
                    components=[],
                )
                session.add(
                    Message(
                        contact_phone=contact.phone,
                        direction=MessageDirection.outbound,
                        body="[review_request]",
                        status=MessageStatus.sent,
                        wa_message_id=wa_msg_id,
                        template_name="review_request",
                    )
                )
            except Exception as exc:
                logger.warning("Failed to send review_request to %s: %s", contact.phone, exc)

        await session.commit()
