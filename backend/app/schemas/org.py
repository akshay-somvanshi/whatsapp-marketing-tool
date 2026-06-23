import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.user import Role


class OrgOut(BaseModel):
    """Org settings with secrets masked — only booleans indicate whether set."""

    id: uuid.UUID
    name: str
    slug: str
    whatsapp_phone_number_id: str | None
    whatsapp_business_account_id: str | None
    ai_provider: str
    system_prompt: str | None
    whatsapp_api_token_set: bool
    anthropic_api_key_set: bool
    gemini_api_key_set: bool
    created_at: datetime


_VALID_AI_PROVIDERS = {"anthropic", "gemini"}


class OrgUpdate(BaseModel):
    name: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_token: str | None = None
    whatsapp_business_account_id: str | None = None
    ai_provider: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    system_prompt: str | None = None

    @field_validator("ai_provider")
    @classmethod
    def validate_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_AI_PROVIDERS:
            raise ValueError(f"ai_provider must be one of {sorted(_VALID_AI_PROVIDERS)}")
        return v


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: Role
    created_at: datetime


class AddMemberRequest(BaseModel):
    email: str
    role: Role = Role.agent
    # Required only when the email does not yet belong to an existing user.
    password: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def not_owner(cls, v: Role) -> Role:
        if v == Role.owner:
            raise ValueError("cannot assign the owner role")
        return v


class UpdateMemberRequest(BaseModel):
    role: Role

    @field_validator("role")
    @classmethod
    def not_owner(cls, v: Role) -> Role:
        if v == Role.owner:
            raise ValueError("cannot assign the owner role")
        return v
