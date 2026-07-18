"""Thin wrapper around M08-P02 Lenco webhook signature verification and ingestion prep."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from app.schemas.base import StrictModel
from app.services.payments.lenco.client import LencoClient
from app.services.payments.lenco.config import get_api_token

LENCO_PROVIDER = "lenco"
SIGNATURE_HEADER = "X-Lenco-Signature"

KNOWN_LENCO_EVENTS = frozenset(
    {
        "collection.successful",
        "collection.failed",
        "collection.settled",
        "transfer.successful",
        "transfer.failed",
        "transaction.credit",
        "transaction.debit",
    }
)


class WebhookIngestionFlag(StrEnum):
    MALFORMED_JSON = "malformed_json"
    UNKNOWN_EVENT_TYPE = "unknown_event_type"
    MISSING_EVENT_ID = "missing_event_id"


class LencoWebhookVerifyResult(StrictModel):
    valid: bool
    event_id: str | None = None
    raw: dict[str, Any] | None = None
    flags: list[str] = []


def _fallback_event_id(raw_body: bytes) -> str:
    digest = hashlib.sha256(raw_body).hexdigest()
    return f"body-{digest}"


def _extract_event_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict):
        event_id = data.get("id")
        if isinstance(event_id, str) and event_id:
            return event_id
    return None


def _compose_webhook_event_id(payload: dict[str, Any], data_id: str) -> str:
    """Disambiguate Lenco events that share the same ``data.id`` (e.g. successful vs settled)."""
    event_name = payload.get("event")
    if isinstance(event_name, str) and event_name.strip():
        return f"{event_name.strip()}:{data_id}"
    return data_id


def _build_raw_document(
    *,
    raw_body: bytes,
    payload: dict[str, Any] | None,
    flags: list[str],
) -> dict[str, Any]:
    document: dict[str, Any] = {"_ingestion": {"flags": flags}}
    if payload is not None:
        document.update(payload)
        return document

    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = raw_body.decode("utf-8", errors="replace")
    document["_ingestion"]["raw_body"] = body_text
    return document


def verify_lenco_webhook(
    *,
    raw_body: bytes,
    signature: str,
    api_token: str | None = None,
) -> LencoWebhookVerifyResult:
    """Verify the Lenco webhook signature on the raw body before any JSON parsing."""
    token = api_token if api_token is not None else get_api_token()
    client = LencoClient(token=token)
    valid = client.verify_webhook_signature(
        raw_body=raw_body,
        signature=signature,
        token=token,
    )
    if not valid:
        return LencoWebhookVerifyResult(valid=False)

    flags: list[str] = []
    payload: dict[str, Any] | None = None
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        flags.append(WebhookIngestionFlag.MALFORMED_JSON.value)
        event_id = _fallback_event_id(raw_body)
        raw = _build_raw_document(raw_body=raw_body, payload=None, flags=flags)
        return LencoWebhookVerifyResult(valid=True, event_id=event_id, raw=raw, flags=flags)

    if not isinstance(decoded, dict):
        flags.append(WebhookIngestionFlag.MALFORMED_JSON.value)
        event_id = _fallback_event_id(raw_body)
        raw = _build_raw_document(raw_body=raw_body, payload=None, flags=flags)
        return LencoWebhookVerifyResult(valid=True, event_id=event_id, raw=raw, flags=flags)

    payload = decoded
    event_name = payload.get("event")
    if not isinstance(event_name, str) or event_name not in KNOWN_LENCO_EVENTS:
        flags.append(WebhookIngestionFlag.UNKNOWN_EVENT_TYPE.value)

    resolved_event_id = _extract_event_id(payload)
    if resolved_event_id is None:
        flags.append(WebhookIngestionFlag.MISSING_EVENT_ID.value)
        event_id = _fallback_event_id(raw_body)
    else:
        event_id = _compose_webhook_event_id(payload, resolved_event_id)

    raw = _build_raw_document(raw_body=raw_body, payload=payload, flags=flags)
    return LencoWebhookVerifyResult(valid=True, event_id=event_id, raw=raw, flags=flags)


def build_webhook_event_row(result: LencoWebhookVerifyResult) -> dict[str, Any]:
    """Shape a `webhook_events` insert row from a verified webhook."""
    if not result.valid or result.event_id is None or result.raw is None:
        msg = "cannot build webhook_events row from an unverified result"
        raise ValueError(msg)

    return {
        "provider": LENCO_PROVIDER,
        "event_id": result.event_id,
        "signature_valid": True,
        "raw": result.raw,
        "processed_at": None,
    }
