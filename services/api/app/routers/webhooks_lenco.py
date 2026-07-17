"""Lenco payment webhook ingestion — verify, persist, fast-ack."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.payments.webhook_verify import (
    SIGNATURE_HEADER,
    build_webhook_event_row,
    verify_lenco_webhook,
)
from fastapi import APIRouter, Depends, Request
from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _is_unique_violation(exc: APIError) -> bool:
    return exc.code == "23505"


async def _persist_webhook_event(
    service_client: _ServiceRoleClient,
    result: Any,
) -> bool:
    """Insert the webhook row. Returns False when the event was already stored."""
    row = build_webhook_event_row(result)
    try:
        service_client.client.table("webhook_events").insert(row).execute()
    except APIError as exc:
        if _is_unique_violation(exc):
            logger.info(
                "Duplicate Lenco webhook ignored",
                extra={"provider": row["provider"], "event_id": row["event_id"]},
            )
            return False
        raise
    return True


@router.post("/lenco")
async def lenco_webhook(
    request: Request,
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER, "")

    # A missing/empty signature header is a client error — reject with a clean 401
    # before attempting verification (which needs the API token). This stops an
    # unsigned request from surfacing as a 500 (OWASP audit finding F2) and keeps a
    # client-side missing-signature (401) distinct from a server-side token
    # misconfiguration (still a 500, correctly, if a *present* signature can't be
    # checked). The payload is never parsed or persisted.
    if not signature.strip():
        logger.warning(
            "Lenco webhook rejected: missing signature header",
            extra={
                "alert": "lenco_webhook_missing_signature",
                "path": request.url.path,
                "body_bytes": len(raw_body),
            },
        )
        raise AppError(
            code="missing_webhook_signature",
            message="Missing Lenco webhook signature",
            http_status=401,
        )

    verified = verify_lenco_webhook(raw_body=raw_body, signature=signature)
    if not verified.valid:
        logger.error(
            "Lenco webhook signature verification failed",
            extra={
                "alert": "lenco_webhook_invalid_signature",
                "path": request.url.path,
                "body_bytes": len(raw_body),
            },
        )
        raise AppError(
            code="invalid_webhook_signature",
            message="Invalid Lenco webhook signature",
            http_status=401,
        )

    stored = await _persist_webhook_event(service_client, verified)
    if stored:
        logger.info(
            "Lenco webhook stored for async processing",
            extra={
                "event_id": verified.event_id,
                "flags": verified.flags,
            },
        )
    return {"status": "accepted"}
