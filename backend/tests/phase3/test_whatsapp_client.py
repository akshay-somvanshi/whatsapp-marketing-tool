"""Phase 3 — WhatsApp client tests."""
import json

import pytest

from app.whatsapp.client import (
    META_API_VERSION,
    OptedOutError,
    WhatsAppAPIError,
    WhatsAppClient,
)

PHONE_NUMBER_ID = "test_phone_id_123"
TEST_TOKEN = "test_bearer_token"


def real_client() -> WhatsAppClient:
    """Return a non-mock client wired to a fake phone_number_id and token."""
    return WhatsAppClient(
        mock=False,
        token=TEST_TOKEN,
        phone_number_id=PHONE_NUMBER_ID,
    )


def mock_client() -> WhatsAppClient:
    return WhatsAppClient(mock=True)


EXPECTED_URL = (
    f"https://graph.facebook.com/{META_API_VERSION}/{PHONE_NUMBER_ID}/messages"
)

# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------


async def test_send_text_message_mock_returns_mock_id():
    result = await mock_client().send_text_message("+919876543210", "Hello!")
    assert result.startswith("mock_")


async def test_send_template_message_mock_returns_mock_id():
    result = await mock_client().send_template_message(
        phone="+919876543210",
        template_name="review_request",
        language_code="en",
        components=[],
    )
    assert result.startswith("mock_")


async def test_mark_as_read_mock_returns_none():
    result = await mock_client().mark_as_read("wamid.fake")
    assert result is None


# ---------------------------------------------------------------------------
# OptedOut guard
# ---------------------------------------------------------------------------


class _FakeContact:
    def __init__(self, phone: str, opted_in: bool) -> None:
        self.phone = phone
        self.opted_in = opted_in


def test_assert_opted_in_raises_for_opted_out_contact():
    contact = _FakeContact(phone="+919876543210", opted_in=False)
    with pytest.raises(OptedOutError):
        WhatsAppClient.assert_opted_in(contact)


def test_assert_opted_in_does_not_raise_for_opted_in_contact():
    contact = _FakeContact(phone="+919876543210", opted_in=True)
    WhatsAppClient.assert_opted_in(contact)  # should not raise


# ---------------------------------------------------------------------------
# Real mode — HTTP interception via pytest-httpx
# ---------------------------------------------------------------------------


async def test_send_text_message_posts_correct_body(httpx_mock):
    httpx_mock.add_response(
        url=EXPECTED_URL,
        json={"messages": [{"id": "wamid.real_text_001"}]},
    )

    result = await real_client().send_text_message("+919876543210", "Hello there")

    assert result == "wamid.real_text_001"
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
    body = json.loads(request.content)
    # Meta's API expects the recipient without a leading "+"; the client strips it.
    assert body["to"] == "919876543210"
    assert body["type"] == "text"
    assert body["text"]["body"] == "Hello there"
    assert body["messaging_product"] == "whatsapp"


async def test_send_template_message_posts_correct_body(httpx_mock):
    httpx_mock.add_response(
        url=EXPECTED_URL,
        json={"messages": [{"id": "wamid.real_tmpl_002"}]},
    )
    components = [{"type": "body", "parameters": [{"type": "text", "text": "Priya"}]}]

    result = await real_client().send_template_message(
        phone="+919876543210",
        template_name="review_request",
        language_code="en_US",
        components=components,
    )

    assert result == "wamid.real_tmpl_002"
    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["type"] == "template"
    assert body["template"]["name"] == "review_request"
    assert body["template"]["language"]["code"] == "en_US"
    assert body["template"]["components"] == components


async def test_mark_as_read_posts_correct_body(httpx_mock):
    httpx_mock.add_response(url=EXPECTED_URL, json={"success": True})

    await real_client().mark_as_read("wamid.inbound_abc")

    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert body["status"] == "read"
    assert body["message_id"] == "wamid.inbound_abc"
    assert body["messaging_product"] == "whatsapp"


async def test_api_error_raises_whatsapp_api_error(httpx_mock):
    httpx_mock.add_response(url=EXPECTED_URL, status_code=401, text="Unauthorized")

    with pytest.raises(WhatsAppAPIError, match="401"):
        await real_client().send_text_message("+919876543210", "Test")
