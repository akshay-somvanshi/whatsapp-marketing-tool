import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AuthContext, get_current_context, require_role
from app.models.organization import Organization
from app.models.user import Membership, Role, User
from app.schemas.org import (
    AddMemberRequest,
    MemberOut,
    OrgOut,
    OrgUpdate,
    UpdateMemberRequest,
)
from app.security import hash_password

router = APIRouter(prefix="/org", tags=["org"])


def _org_out(org: Organization) -> OrgOut:
    return OrgOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        whatsapp_phone_number_id=org.whatsapp_phone_number_id,
        whatsapp_business_account_id=org.whatsapp_business_account_id,
        ai_provider=org.ai_provider,
        system_prompt=org.system_prompt,
        whatsapp_api_token_set=bool(org.whatsapp_api_token),
        anthropic_api_key_set=bool(org.anthropic_api_key),
        gemini_api_key_set=bool(org.gemini_api_key),
        created_at=org.created_at,
    )


async def _get_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = (
        await db.execute(sa.select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("", response_model=OrgOut)
async def get_org(
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    return _org_out(await _get_org(db, ctx.organization_id))


@router.patch("", response_model=OrgOut)
async def update_org(
    data: OrgUpdate,
    ctx: AuthContext = Depends(require_role(Role.owner, Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org(db, ctx.organization_id)
    for field in (
        "name",
        "whatsapp_phone_number_id",
        "whatsapp_api_token",
        "whatsapp_business_account_id",
        "ai_provider",
        "anthropic_api_key",
        "gemini_api_key",
        "system_prompt",
    ):
        value = getattr(data, field)
        if value is not None:
            setattr(org, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That WhatsApp phone number is already used by another organization",
        )
    await db.refresh(org)
    return _org_out(org)


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            sa.select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == ctx.organization_id)
            .order_by(Membership.created_at.asc())
        )
    ).all()
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=m.role,
            created_at=m.created_at,
        )
        for m, user in rows
    ]


@router.post("/members", response_model=MemberOut, status_code=201)
async def add_member(
    data: AddMemberRequest,
    ctx: AuthContext = Depends(require_role(Role.owner)),
    db: AsyncSession = Depends(get_db),
):
    user = (
        await db.execute(sa.select(User).where(User.email == data.email))
    ).scalar_one_or_none()

    if user is None:
        if not data.password or len(data.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="New user requires a password of at least 8 characters",
            )
        user = User(email=data.email, password_hash=hash_password(data.password))
        db.add(user)
        await db.flush()

    existing = (
        await db.execute(
            sa.select(Membership).where(
                Membership.user_id == user.id,
                Membership.organization_id == ctx.organization_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="User is already a member")

    membership = Membership(
        user_id=user.id, organization_id=ctx.organization_id, role=data.role
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.patch("/members/{user_id}", response_model=MemberOut)
async def update_member(
    user_id: uuid.UUID,
    data: UpdateMemberRequest,
    ctx: AuthContext = Depends(require_role(Role.owner)),
    db: AsyncSession = Depends(get_db),
):
    if user_id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    membership = (
        await db.execute(
            sa.select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == ctx.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if membership.role == Role.owner:
        raise HTTPException(status_code=400, detail="Cannot change the owner's role")

    membership.role = data.role
    await db.commit()
    await db.refresh(membership)

    user = (
        await db.execute(sa.select(User).where(User.id == user_id))
    ).scalar_one()
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(Role.owner)),
    db: AsyncSession = Depends(get_db),
):
    if user_id == ctx.user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    membership = (
        await db.execute(
            sa.select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == ctx.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if membership.role == Role.owner:
        raise HTTPException(status_code=400, detail="Cannot remove the owner")

    await db.delete(membership)
    await db.commit()
