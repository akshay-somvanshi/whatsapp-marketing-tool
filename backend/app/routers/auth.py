import re
import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AuthContext, get_current_context
from app.models.organization import Organization
from app.models.user import Membership, Role, User
from app.schemas.auth import (
    LoginRequest,
    MembershipOut,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:6]}"


async def _memberships_out(db: AsyncSession, user_id: uuid.UUID) -> list[MembershipOut]:
    rows = (
        await db.execute(
            sa.select(Membership, Organization.name)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at.asc())
        )
    ).all()
    return [
        MembershipOut(
            organization_id=m.organization_id,
            organization_name=org_name,
            role=m.role,
        )
        for m, org_name in rows
    ]


def _tokens_for(user_id: uuid.UUID, organization_id: uuid.UUID, role: Role) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user_id=user_id, organization_id=organization_id, role=role.value
        ),
        refresh_token=create_refresh_token(user_id=user_id),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(sa.select(User).where(User.email == data.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    org = Organization(name=data.organization_name, slug=_slugify(data.organization_name))
    db.add_all([user, org])
    await db.flush()

    membership = Membership(user_id=user.id, organization_id=org.id, role=Role.owner)
    db.add(membership)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent registration with the same email lost the race to the
        # users.email unique constraint.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")

    return _tokens_for(user.id, org.id, Role.owner)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(sa.select(User).where(User.email == data.email))
    ).scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Default to the earliest membership (typically the org they created).
    membership = (
        await db.execute(
            sa.select(Membership)
            .where(Membership.user_id == user.id)
            .order_by(Membership.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="User has no organization")

    return _tokens_for(user.id, membership.organization_id, membership.role)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token, expected_type="refresh")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    user = (
        await db.execute(sa.select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    membership = (
        await db.execute(
            sa.select(Membership)
            .where(Membership.user_id == user.id)
            .order_by(Membership.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="User has no organization")

    return _tokens_for(user.id, membership.organization_id, membership.role)


@router.get("/me", response_model=UserOut)
async def me(
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    return UserOut(
        id=ctx.user.id,
        email=ctx.user.email,
        full_name=ctx.user.full_name,
        memberships=await _memberships_out(db, ctx.user.id),
    )
