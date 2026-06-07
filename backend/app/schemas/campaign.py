import json
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.campaign import CampaignStatus

_TEMPLATES_PATH = Path(__file__).resolve().parent.parent.parent / "templates.json"
_templates_cache: list[dict] | None = None


def _get_templates() -> list[dict]:
    global _templates_cache
    if _templates_cache is None:
        with open(_TEMPLATES_PATH) as f:
            _templates_cache = json.load(f)
    return _templates_cache


class CampaignCreate(BaseModel):
    name: str
    template_name: str
    template_params: dict = {}
    audience_tags: list[str] = []
    scheduled_at: datetime | None = None

    @field_validator("template_name")
    @classmethod
    def validate_template(cls, v: str) -> str:
        valid = {t["name"] for t in _get_templates()}
        if v not in valid:
            raise ValueError(f"template '{v}' not found in templates.json")
        return v


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    template_name: str
    template_params: dict
    audience_tags: list[str]
    scheduled_at: datetime | None
    status: CampaignStatus
    sent_count: int
    delivered_count: int
    read_count: int
    created_at: datetime
