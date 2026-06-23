"""Auth dependencies: resolve the current user/org/role from the access token."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import Membership, Role, User
from app.security import TokenError, decode_token

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """The authenticated principal for a request, scoped to one organization."""

    user: User
    organization_id: uuid.UUID
    role: Role


async def get_current_context(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    try:
        user_id = uuid.UUID(payload["sub"])
        org_id = uuid.UUID(payload["org"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    user = (
        await db.execute(sa.select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Re-validate membership live so role changes / removals take effect immediately.
    membership = (
        await db.execute(
            sa.select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    return AuthContext(user=user, organization_id=org_id, role=membership.role)


def require_role(*allowed: Role):
    """Dependency factory: require the current member to hold one of `allowed`."""

    async def _checker(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
        if ctx.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return ctx

    return _checker
