"""Best-effort async dispatch of domain events to the configured n8n webhook.

External webhook delivery is treated as untrusted/unreliable: failures are logged
and swallowed so a notification problem never rolls back a successful transaction.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from app.settings import Settings, get_settings
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

_DISPATCH_TIMEOUT_SECONDS = 10.0


def build_n8n_payload(*, event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Shape a webhook body n8n workflows can branch on via ``$json.event``."""
    return {"event": event, **data}


def post_n8n_webhook(payload: dict[str, Any], *, settings: Settings | None = None) -> None:
    """POST to ``N8N_WEBHOOK_URL``. Never raises — safe for background tasks."""
    cfg = settings or get_settings()
    url = cfg.n8n_webhook_url.strip()
    if not url:
        return

    try:
        with httpx.Client(timeout=_DISPATCH_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
    except Exception:
        logger.warning(
            "n8n webhook dispatch failed",
            extra={"event": payload.get("event"), "url_configured": True},
            exc_info=True,
        )


def schedule_n8n_webhook(
    background_tasks: BackgroundTasks,
    *,
    event: str,
    data: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    """Queue a fire-and-forget n8n POST after the HTTP response is sent."""
    payload = build_n8n_payload(event=event, data=data)
    cfg = settings or get_settings()
    background_tasks.add_task(post_n8n_webhook, payload, settings=cfg)
