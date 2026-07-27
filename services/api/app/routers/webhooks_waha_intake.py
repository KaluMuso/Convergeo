"""M18-P02 — isolated WAHA vendor-intake webhook (D35 Lane 2).

**This is not Lane 1.** ``app.routers.webhooks_whatsapp`` handles the official
Meta Cloud API and is untouched by this module: nothing is imported from it, and
Meta's ``X-Hub-Signature-256`` / ``verify_hub_signature`` scheme is deliberately
**not** reused. WAHA's pinned ``2026.5.1`` contract is different — an
HMAC-**SHA-512** over the raw body in ``X-Webhook-Hmac`` — and conflating the two
would let a signature valid for one lane authenticate the other.

Ten gates, in order, all fail-closed. Any failure drops the event, audits the
disposition, and returns without touching the domain::

    1. flag          — the kill switch, checked before anything is parsed
    2. HMAC          — sha512 over raw bytes, constant-time
    3. request id + timestamp freshness
    4. source account
    5. event type    — only the session `message` event
    6. direct chat   — groups/broadcast/status categorically dropped
    7. sender shape
    8. verified vendor + pilot allowlist
    9. schema
    10. replay dedupe (after auth + schema, per §7)

**Strictly inbound-only.** This module constructs no client and sends nothing:
no ack, no reply, no read receipt. The corrected D35 removed the previously
permitted receipt acknowledgement.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Annotated, Any, Final

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.intake import config as intake_config
from app.services.intake import normalise as waha_normalise
from app.services.intake import sessions, state_machine
from fastapi import APIRouter, Depends, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks-waha-intake"])

# --- WAHA 2026.5.1 headers --------------------------------------------------
HEADER_HMAC: Final = "X-Webhook-Hmac"
HEADER_HMAC_ALGO: Final = "X-Webhook-Hmac-Algorithm"
HEADER_REQUEST_ID: Final = "X-Webhook-Request-Id"
HEADER_TIMESTAMP: Final = "X-Webhook-Timestamp"

# The contract pins exactly one algorithm. Accepting a second would be an
# algorithm-confusion foothold.
REQUIRED_HMAC_ALGORITHM: Final = "sha512"

# Freshness window for X-Webhook-Timestamp (Unix milliseconds).
MAX_CLOCK_SKEW_SECONDS: Final = 300

WEBHOOK_EVENTS_TABLE: Final = "webhook_events"
PROVIDER: Final = "waha"

# Cap the body we will even hash, so a huge POST cannot be used to burn CPU.
MAX_BODY_BYTES: Final = 1_048_576


def _mask_msisdn(value: str) -> str:
    return f"***{value[-3:]}" if len(value) >= 3 else "***"


def _audit(
    service_client: Any,
    *,
    disposition: str,
    event_id: str | None = None,
    vendor_id: str | None = None,
    session_id: str | None = None,
    message_kind: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Record the disposition, never letting an audit failure mask the drop."""
    try:
        state_machine.record_ingestion(
            service_client,
            disposition=disposition,
            vendor_id=vendor_id,
            session_id=session_id,
            provider_event_id=event_id,
            message_kind=message_kind,
            detail=detail or {},
        )
    except Exception:  # pragma: no cover - audit must never raise into the gate
        logger.warning("intake audit write failed", extra={"disposition": disposition})


def _verify_signature(raw_body: bytes, headers: Any) -> bool:
    """Verify WAHA's HMAC-SHA-512 over the exact raw body. Fail closed."""
    algorithm = (headers.get(HEADER_HMAC_ALGO) or "").strip().lower()
    if algorithm != REQUIRED_HMAC_ALGORITHM:
        return False

    provided = (headers.get(HEADER_HMAC) or "").strip()
    if not provided:
        return False

    try:
        secret = intake_config.webhook_secret()
    except AppError:
        # No secret configured ⇒ verification fails closed. It must never
        # degrade into "accept everything".
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, provided.lower())


def _timestamp_fresh(headers: Any) -> bool:
    """Require a present, parseable, recent X-Webhook-Timestamp (ms)."""
    raw = (headers.get(HEADER_TIMESTAMP) or "").strip()
    if not raw:
        return False
    try:
        stamp_ms = int(raw)
    except (TypeError, ValueError):
        return False
    delta = abs(time.time() - (stamp_ms / 1000.0))
    return delta <= MAX_CLOCK_SKEW_SECONDS


def _claim_event(service_client: Any, event_id: str) -> bool:
    """Insert the dedupe row. False ⇒ already seen (replay), so do nothing."""
    try:
        service_client.client.table(WEBHOOK_EVENTS_TABLE).insert(
            {"provider": PROVIDER, "event_id": event_id}
        ).execute()
    except Exception:
        # A unique violation is the expected replay path. Any other failure
        # also resolves to "do not process twice", which is the safe direction.
        return False
    return True


@router.post("/waha-intake")
async def receive_waha_intake(
    request: Request,
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> Response:
    """Ingest one inbound WAHA vendor-intake event. Sends nothing, ever."""

    # --- Gate 1: the kill switch, before anything is parsed -----------------
    if not intake_config.intake_enabled(service_client):
        _audit(service_client, disposition=state_machine.DISPOSITION_DROPPED_FLAG_OFF)
        # 200, not 403: a disabled lane must not advertise its own existence
        # through a distinguishable status code.
        return Response(status_code=200)

    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        _audit(service_client, disposition=state_machine.DISPOSITION_REJECTED_AUTH)
        return Response(status_code=413)

    # --- Gate 2: HMAC-SHA-512 over the raw bytes, before any JSON parse -----
    if not _verify_signature(raw_body, request.headers):
        _audit(service_client, disposition=state_machine.DISPOSITION_REJECTED_AUTH)
        return Response(status_code=403)

    # --- Gate 3: request identity + freshness --------------------------------
    if not (request.headers.get(HEADER_REQUEST_ID) or "").strip():
        _audit(service_client, disposition=state_machine.DISPOSITION_REJECTED_AUTH)
        return Response(status_code=403)
    if not _timestamp_fresh(request.headers):
        _audit(service_client, disposition=state_machine.DISPOSITION_REJECTED_AUTH)
        return Response(status_code=403)

    # Only now is it safe to look at the body's contents.
    try:
        payload = await request.json()
    except Exception:
        _audit(service_client, disposition=state_machine.DISPOSITION_ERROR)
        return Response(status_code=400)

    # --- Gates 5 + 9: pinned event shape (normalisation is strict) ----------
    try:
        event = waha_normalise.normalise(payload)
    except waha_normalise.NormalisationError:
        _audit(service_client, disposition=state_machine.DISPOSITION_ERROR)
        return Response(status_code=400)

    # --- Gate 4: source account ---------------------------------------------
    try:
        expected_session = intake_config.session_name()
    except AppError:
        _audit(service_client, disposition=state_machine.DISPOSITION_REJECTED_AUTH)
        return Response(status_code=503)
    if event.session != expected_session:
        _audit(
            service_client,
            disposition=state_machine.DISPOSITION_REJECTED_AUTH,
            event_id=event.event_id,
        )
        return Response(status_code=403)

    # --- Gate 6: direct chat only. Groups are categorically forbidden -------
    # Positive check: it must BE an individual chat, not merely "not a known
    # group shape". An unfamiliar conversation type is refused by default.
    if not event.is_individual_chat:
        _audit(
            service_client,
            disposition=state_machine.DISPOSITION_DROPPED_GROUP,
            event_id=event.event_id,
        )
        return Response(status_code=200)

    # --- Gate 7: sender shape ------------------------------------------------
    msisdn = sessions.normalise_msisdn(event.sender_msisdn_raw)
    if msisdn is None:
        _audit(
            service_client,
            disposition=state_machine.DISPOSITION_DROPPED_UNVERIFIED,
            event_id=event.event_id,
        )
        return Response(status_code=200)

    # --- Gate 8: known verified sender + pilot allowlist ---------------------
    sender = sessions.resolve_verified_sender(service_client, msisdn)
    if sender is None or not intake_config.vendor_allowlisted(service_client, sender.vendor_id):
        # Identical handling for unknown, ineligible, and not-allowlisted, so
        # the response cannot be used to probe whether an account exists.
        _audit(
            service_client,
            disposition=state_machine.DISPOSITION_DROPPED_UNVERIFIED,
            event_id=event.event_id,
        )
        return Response(status_code=200)

    # --- Gate 10: replay dedupe, after auth + schema (§7 ordering) ----------
    if not _claim_event(service_client, event.event_id):
        return Response(status_code=200)

    sessions.record_inbound(
        service_client,
        sender=sender,
        provider_message_id=event.event_id,
        kind=event.kind,
        raw_excerpt=event.text,
    )

    logger.info(
        "intake event accepted",
        extra={"event_id": event.event_id, "msisdn": _mask_msisdn(msisdn)},
    )
    return Response(status_code=200)
