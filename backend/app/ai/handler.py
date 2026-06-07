from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
_system_prompt_cache: str | None = None

_VALID_ACTIONS = {"reply", "escalate", "save_review"}
_STUB_RESPONSE: dict = {"action": "reply", "text": "Thank you for your message!"}


def _load_system_prompt() -> str:
    global _system_prompt_cache
    if _system_prompt_cache is None:
        _system_prompt_cache = _SYSTEM_PROMPT_PATH.read_text()
    return _system_prompt_cache


def _parse_action(raw: str) -> dict:
    """Parse a JSON action dict from Claude's raw output, with fallbacks."""
    text = raw.strip()
    # Strip markdown code fences when present
    if text.startswith("```"):
        parts = text.split("```")
        inner = parts[1] if len(parts) >= 2 else ""
        if inner.startswith("json"):
            inner = inner[4:]
        text = inner.strip()
    try:
        action = json.loads(text)
    except json.JSONDecodeError:
        return {"action": "reply", "text": raw}
    if not isinstance(action, dict) or action.get("action") not in _VALID_ACTIONS:
        return {"action": "reply", "text": raw}
    return action


async def generate_reply(
    messages: list[dict[str, str]],
    contact_name: str,
    system_prompt: str = "",
) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        return _STUB_RESPONSE

    base_prompt = system_prompt or _load_system_prompt()
    full_system = base_prompt.replace("{contact_name}", contact_name)

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=full_system,
        messages=messages,
    )

    raw = response.content[0].text
    return _parse_action(raw)
