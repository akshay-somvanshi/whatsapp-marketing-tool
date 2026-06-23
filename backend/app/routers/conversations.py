import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AuthContext, get_current_context
from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection, MessageStatus
from app.models.organization import Organization
from app.schemas.conversation import (
    ConversationDetail,
    ConversationOut,
    ConversationPatch,
    MessageOut,
    SendMessageRequest,
)
from app.whatsapp.client import client_for_org

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa.select(Conversation)
        .where(Conversation.organization_id == ctx.organization_id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{phone}", response_model=ConversationDetail)
async def get_conversation(
    phone: str,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa.select(Conversation).where(
            Conversation.organization_id == ctx.organization_id,
            Conversation.contact_phone == phone,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await db.execute(
        sa.select(Message)
        .where(
            Message.organization_id == ctx.organization_id,
            Message.contact_phone == phone,
        )
        .order_by(Message.created_at.asc())
    )

    return ConversationDetail(
        id=conv.id,
        contact_phone=conv.contact_phone,
        status=conv.status,
        ai_enabled=conv.ai_enabled,
        session_expires_at=conv.session_expires_at,
        updated_at=conv.updated_at,
        messages=list(msgs.scalars().all()),
    )


@router.patch("/{phone}", response_model=ConversationOut)
async def patch_conversation(
    phone: str,
    data: ConversationPatch,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa.select(Conversation).where(
            Conversation.organization_id == ctx.organization_id,
            Conversation.contact_phone == phone,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.ai_enabled = data.ai_enabled
    await db.commit()
    await db.refresh(conv)
    return conv


@router.post("/{phone}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    phone: str,
    data: SendMessageRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa.select(Conversation).where(
            Conversation.organization_id == ctx.organization_id,
            Conversation.contact_phone == phone,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    org = (
        await db.execute(
            sa.select(Organization).where(Organization.id == ctx.organization_id)
        )
    ).scalar_one()

    wa_msg_id = await client_for_org(org).send_text_message(phone, data.text)
    msg = Message(
        organization_id=ctx.organization_id,
        contact_phone=phone,
        direction=MessageDirection.outbound,
        body=data.text,
        status=MessageStatus.sent,
        wa_message_id=wa_msg_id,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg
