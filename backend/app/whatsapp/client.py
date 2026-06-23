"""
WhatsApp Cloud API client.

When settings.MOCK_WHATSAPP is True every method short-circuits: it logs
to stdout and returns a fake message ID prefixed with "mock_".  This lets
the full app flow run locally without Meta credentials.

Consent is NOT enforced inside send methods — callers are responsible for
filtering opted-out contacts before calling.  Use assert_opted_in() as an
explicit guard wherever needed.
"""

import logging
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

META_API_VERSION = "v19.0"
META_GRAPH_BASE = "https://graph.facebook.com"


class OptedOutError(Exception):
    """Raised when assert_opted_in() is called for an opted-out contact."""


class WhatsAppAPIError(Exception):
    """Raised when the Meta Graph API returns a non-2xx response."""


class WhatsAppClient:
    def __init__(
        self,
        *,
        mock: bool = False,
        token: str = "",
        phone_number_id: str = "",
    ) -> None:
        self.mock = mock
        self.token = token
        self.phone_number_id = phone_number_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def assert_opted_in(contact) -> None:
        """Raise OptedOutError if contact.opted_in is False."""
        if not contact.opted_in:
            raise OptedOutError(
                f"Contact {contact.phone} has opted out and cannot receive messages."
            )

    async def send_text_message(self, phone: str, text: str) -> str:
        """Send a free-form text message within a 24-hour session window."""
        if self.mock:
            msg_id = f"mock_{uuid.uuid4()}"
            logger.info("[MOCK WA] send_text_message → %s: %r  id=%s", phone, text, msg_id)
            return msg_id

        payload = {
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "text",
            "text": {"body": text},
        }
        return await self._post_messages(payload)

    async def send_template_message(
        self,
        phone: str,
        template_name: str,
        language_code: str,
        components: list[dict],
    ) -> str:
        """Send a pre-approved template message (works outside the session window)."""
        if self.mock:
            msg_id = f"mock_{uuid.uuid4()}"
            logger.info(
                "[MOCK WA] send_template_message → %s: template=%s  id=%s",
                phone,
                template_name,
                msg_id,
            )
            return msg_id

        payload = {
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        return await self._post_messages(payload)

    async def mark_as_read(self, wa_message_id: str) -> None:
        """Send a read receipt for an inbound message."""
        if self.mock:
            logger.info("[MOCK WA] mark_as_read: %s", wa_message_id)
            return

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wa_message_id,
        }
        await self._post(payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _messages_url(self) -> str:
        return f"{META_GRAPH_BASE}/{META_API_VERSION}/{self.phone_number_id}/messages"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _post_messages(self, payload: dict) -> str:
        """POST to /messages and return the wa_message_id from the response."""
        data = await self._post(payload)
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise WhatsAppAPIError(f"Unexpected Meta response shape: {data}") from exc

    async def _post(self, payload: dict) -> dict:
        """POST payload to the messages endpoint; raise WhatsAppAPIError on failure."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._messages_url(),
                json=payload,
                headers=self._auth_headers(),
            )

        if resp.is_error:
            raise WhatsAppAPIError(
                f"Meta API error {resp.status_code}: {resp.text}"
            )

        return resp.json()


# ---------------------------------------------------------------------------
# Module-level singleton — global/dev client (mock or env-configured).
# ---------------------------------------------------------------------------
wa_client = WhatsAppClient(
    mock=settings.MOCK_WHATSAPP,
    token=settings.WHATSAPP_API_TOKEN,
    phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
)


def client_for_org(org) -> "WhatsAppClient":
    """Build a WhatsApp client using a specific organization's credentials.

    In mock mode every org shares the global mock client (no real calls).
    In live mode the org's own token + phone_number_id are used so each tenant
    sends from its own WhatsApp number.
    """
    if settings.MOCK_WHATSAPP:
        return wa_client
    return WhatsAppClient(
        mock=False,
        token=org.whatsapp_api_token or settings.WHATSAPP_API_TOKEN,
        phone_number_id=org.whatsapp_phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID,
    )
