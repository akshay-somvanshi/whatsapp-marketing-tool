import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.tasks.celery_app import process_inbound_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta webhook verification handshake (GET challenge-response)."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook", status_code=200)
async def receive_webhook(request: Request):
    """
    Receive inbound events from Meta.

    Always returns 200 immediately so Meta doesn't retry.
    Processing is delegated to the Celery task queue.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}
    process_inbound_message.delay(payload)
    return {"status": "ok"}
