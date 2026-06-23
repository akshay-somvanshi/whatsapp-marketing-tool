"""Password hashing and JWT encode/decode helpers.

Stateless auth: access tokens are short-lived and carry the active
organization + role; refresh tokens are long-lived and only identify the user.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or the wrong type."""


# ── Passwords ────────────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────


def _encode(claims: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {**claims, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(*, user_id: uuid.UUID, organization_id: uuid.UUID, role: str) -> str:
    return _encode(
        {
            "sub": str(user_id),
            "org": str(organization_id),
            "role": role,
            "type": "access",
        },
        timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN),
    )


def create_refresh_token(*, user_id: uuid.UUID) -> str:
    return _encode(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    """Decode and validate a token, asserting its `type` claim. Raises TokenError."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token, got {payload.get('type')}")
    return payload
