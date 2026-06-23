"""Phase 7 — AI handler unit tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.handler import _parse_action, generate_reply


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_anthropic_response(text: str):
    """Build a fake anthropic response object with a single text content block."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


@pytest.fixture
def anthropic_client(monkeypatch):
    """
    Patches anthropic.AsyncAnthropic so no real HTTP calls are made.
    Returns the AsyncMock for messages.create so tests can set return_value.
    """
    mock_create = AsyncMock()
    mock_client = MagicMock()
    mock_client.messages.create = mock_create
    monkeypatch.setattr("app.ai.handler.anthropic.AsyncAnthropic", lambda **kwargs: mock_client)
    return mock_create


@pytest.fixture
def with_api_key(monkeypatch):
    """Set a non-empty Anthropic key (and empty Gemini key) so generate_reply
    deterministically routes to the mocked Anthropic client rather than stub/Gemini."""
    monkeypatch.setattr(
        "app.ai.handler.settings",
        MagicMock(ANTHROPIC_API_KEY="test-key", GEMINI_API_KEY=""),
    )


# ---------------------------------------------------------------------------
# _parse_action unit tests (pure function, no async)
# ---------------------------------------------------------------------------


def test_parse_valid_reply_action():
    result = _parse_action('{"action": "reply", "text": "We have lovely gold bangles!"}')
    assert result == {"action": "reply", "text": "We have lovely gold bangles!"}


def test_parse_valid_escalate_action():
    result = _parse_action('{"action": "escalate", "text": "Connecting you now."}')
    assert result["action"] == "escalate"


def test_parse_valid_save_review_action():
    raw = '{"action": "save_review", "review": "Loved the ring!", "text": "Thank you!"}'
    result = _parse_action(raw)
    assert result["action"] == "save_review"
    assert result["review"] == "Loved the ring!"


def test_parse_malformed_json_falls_back_to_reply():
    result = _parse_action("This is not JSON at all")
    assert result["action"] == "reply"
    assert "This is not JSON at all" in result["text"]


def test_parse_unknown_action_falls_back_to_reply():
    result = _parse_action('{"action": "unknown_action", "text": "..."}')
    assert result["action"] == "reply"


def test_parse_markdown_fenced_json():
    fenced = '```json\n{"action": "reply", "text": "Hello!"}\n```'
    result = _parse_action(fenced)
    assert result == {"action": "reply", "text": "Hello!"}


def test_parse_markdown_fenced_without_language_tag():
    fenced = '```\n{"action": "escalate", "text": "One moment."}\n```'
    result = _parse_action(fenced)
    assert result["action"] == "escalate"


# ---------------------------------------------------------------------------
# generate_reply integration tests (async, mocked Anthropic client)
# ---------------------------------------------------------------------------


async def test_stub_returned_when_api_key_empty(monkeypatch):
    monkeypatch.setattr(
        "app.ai.handler.settings",
        MagicMock(ANTHROPIC_API_KEY="", GEMINI_API_KEY=""),
    )
    result = await generate_reply([{"role": "user", "content": "Hi"}], contact_name="Priya")
    assert result == {"action": "reply", "text": "Thank you for your message!"}


async def test_reply_action_from_api(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response(
        '{"action": "reply", "text": "Our store is open 10am–8pm daily."}'
    )
    result = await generate_reply(
        [{"role": "user", "content": "What are your hours?"}],
        contact_name="Priya",
    )
    assert result["action"] == "reply"
    assert "10am" in result["text"]


async def test_escalate_action_from_api(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response(
        '{"action": "escalate", "text": "Connecting you to our team."}'
    )
    result = await generate_reply(
        [{"role": "user", "content": "I want to speak to a manager!"}],
        contact_name="Rahul",
    )
    assert result["action"] == "escalate"


async def test_save_review_action_from_api(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response(
        '{"action": "save_review", "review": "The gold bangle is stunning!", "text": "Thank you for your feedback!"}'
    )
    result = await generate_reply(
        [{"role": "user", "content": "I love my new bangle, it's stunning!"}],
        contact_name="Meena",
    )
    assert result["action"] == "save_review"
    assert result["review"] == "The gold bangle is stunning!"
    assert result["text"] == "Thank you for your feedback!"


async def test_malformed_api_response_falls_back_to_reply(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response("Sure, I can help you with that.")
    result = await generate_reply(
        [{"role": "user", "content": "Any new arrivals?"}],
        contact_name="Kavya",
    )
    assert result["action"] == "reply"
    assert "Sure, I can help" in result["text"]


async def test_contact_name_substituted_in_system_prompt(anthropic_client, with_api_key):
    """Verify {contact_name} in the default system prompt is replaced before the API call."""
    anthropic_client.return_value = _mock_anthropic_response('{"action": "reply", "text": "Hi!"}')
    await generate_reply(
        [{"role": "user", "content": "Hello"}],
        contact_name="Anjali",
    )
    call_kwargs = anthropic_client.call_args.kwargs
    assert "Anjali" in call_kwargs["system"]
    assert "{contact_name}" not in call_kwargs["system"]


async def test_custom_system_prompt_overrides_default(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response('{"action": "reply", "text": "Hi!"}')
    await generate_reply(
        [{"role": "user", "content": "Hello"}],
        contact_name="Dev",
        system_prompt="Custom prompt for {contact_name}.",
    )
    call_kwargs = anthropic_client.call_args.kwargs
    assert call_kwargs["system"] == "Custom prompt for Dev."


async def test_correct_model_and_max_tokens_used(anthropic_client, with_api_key):
    anthropic_client.return_value = _mock_anthropic_response('{"action": "reply", "text": "OK"}')
    await generate_reply([{"role": "user", "content": "Hi"}], contact_name="Test")
    call_kwargs = anthropic_client.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 500
