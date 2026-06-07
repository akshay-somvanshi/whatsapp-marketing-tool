import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationDetail, ConversationOut, ConversationPatch

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa.select(Conversation).order_by(Conversation.updated_at.desc()))
    return result.scalars().all()


@router.get("/{phone}", response_model=ConversationDetail)
async def get_conversation(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        sa.select(Conversation).where(Conversation.contact_phone == phone)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await db.execute(
        sa.select(Message)
        .where(Message.contact_phone == phone)
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
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa.select(Conversation).where(Conversation.contact_phone == phone)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.ai_enabled = data.ai_enabled
    await db.commit()
    await db.refresh(conv)
    return conv
