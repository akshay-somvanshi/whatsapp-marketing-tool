"""
AI conversation handler.

Stub for Phase 4 — returns a canned reply so the full webhook flow can be
tested end-to-end without a real Claude API key.
Phase 7 replaces the body of generate_reply with an actual Anthropic call.
"""
from __future__ import annotations


async def generate_reply(
    messages: list[dict[str, str]],
    contact_name: str,
    system_prompt: str = "",
) -> dict:
    """
    Stub: always replies with a generic message.
    Phase 7 implementation: calls Claude claude-sonnet-4-6, max_tokens=500.
    """
    return {"action": "reply", "text": "Thank you for your message!"}
