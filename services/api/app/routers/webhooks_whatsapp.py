"""Meta WhatsApp Cloud API webhook: verify handshake, delivery status, STOP/START."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from app.deps import get_supabase_client
from app.errors import AppError
from app.services.notifications.dedupe import enqueue_outbox_row, split_dedupe_key
from app.services.notifications.dispatcher import (
    TemplateClass,
    get_template_class,
    has_any_channel_enabled,
)
from app.services.notifications.fallback import (
    CHANNEL_WHATSAPP as FALLBACK_CHANNEL_WHATSAPP,
)
from app.services.notifications.fallback import (
    DeliveryContext,
    enqueue_fallback_row,
    evaluate_lifecycle_fallback,
)
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks-whatsapp"])

_VERIFY_TOKEN_ENV = "WHATSAPP_WEBHOOK_VERIFY_TOKEN"
_APP_SECRET_ENV = "WHATSAPP_APP_SECRET"
_APP_SECRET_FALLBACK_ENV = "META_APP_SECRET"

OUTBOX_TABLE = "notification_outbox"
PROFILES_TABLE = "profiles"
CHANNEL_WHATSAPP = "whatsapp"
EVENT_OPT_STOP = "whatsapp_opt_stop"
EVENT_OPT_START = "whatsapp_opt_start"
TEMPLATE_COMPLIANCE_CONFIRMATION = "compliance_confirmation"
_NOTIFICATIONS_I18N_DIR_ENV = "VERGEO5_NOTIFICATIONS_I18N_DIR"


@lru_cache(maxsize=1)
def _notifications_i18n_dir() -> Path | None:
    override = os.environ.get(_NOTIFICATIONS_I18N_DIR_ENV, "").strip()
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "i18n" / "messages"
        if candidate.is_dir():
            return candidate
    return None

_STOP_KEYWORDS = frozenset({"stop", "unsubscribe", "cancel", "end", "quit"})
_START_KEYWORDS = frozenset({"start", "subscribe", "unstop"})

_DELIVERY_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 0}

_ALL_CHANNELS_OFF = {"whatsapp": False, "sms": False, "email": False}
_ALL_CHANNELS_ON = {"whatsapp": True, "sms": True, "email": True}


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _verify_token() -> str:
    return os.environ.get(_VERIFY_TOKEN_ENV, "").strip()


def _app_secret() -> str:
    secret = os.environ.get(_APP_SECRET_ENV, "").strip()
    if secret:
        return secret
    return os.environ.get(_APP_SECRET_FALLBACK_ENV, "").strip()


def verify_hub_signature(*, raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Validate Meta ``X-Hub-Signature-256`` (HMAC-SHA256 of raw body)."""
    if not signature_header or not app_secret:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    received = signature_header[len(prefix) :]
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


def _normalize_phone_candidates(raw: str) -> list[str]:
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return []
    candidates = [digits]
    if digits.startswith("260"):
        candidates.append(f"+{digits}")
    elif digits.startswith("0") and len(digits) == 10:
        international = f"260{digits[1:]}"
        candidates.extend([international, f"+{international}"])
    if not digits.startswith("+"):
        candidates.append(f"+{digits}")
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for value in candidates:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _map_whatsapp_status(wa_status: str) -> tuple[str, str] | None:
    normalized = wa_status.strip().lower()
    if normalized == "failed":
        return "failed", "failed"
    if normalized == "undelivered":
        return "failed", "undelivered"
    if normalized in {"sent", "delivered", "read"}:
        return "sent", normalized
    return None


def _delivery_should_advance(current: str | None, incoming: str) -> bool:
    if not current:
        return True
    current_rank = _DELIVERY_RANK.get(current.lower(), -1)
    incoming_rank = _DELIVERY_RANK.get(incoming.lower(), -1)
    return incoming_rank > current_rank


def _extract_data(response: object | None) -> Any:
    if response is None:
        return None
    return getattr(response, "data", None)


def _find_outbox_by_message_id(client: Any, message_id: str) -> dict[str, Any] | None:
    response = (
        client.table(OUTBOX_TABLE)
        .select("*")
        .eq("channel", CHANNEL_WHATSAPP)
        .contains("payload", {"whatsapp_message_id": message_id})
        .limit(1)
        .execute()
    )
    data = _extract_data(response)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _apply_status_update(client: Any, row: dict[str, Any], wa_status: str) -> bool:
    """Update outbox status from a WhatsApp delivery callback; idempotent."""
    mapped = _map_whatsapp_status(wa_status)
    if mapped is None:
        return False

    target_status, delivery_status = mapped
    row_id = str(row.get("id", ""))
    if not row_id:
        return False

    current_status = str(row.get("status", ""))
    payload = row.get("payload")
    payload_dict = dict(payload) if isinstance(payload, dict) else {}
    current_delivery = payload_dict.get("delivery_status")
    if isinstance(current_delivery, str):
        current_delivery_str: str | None = current_delivery
    else:
        current_delivery_str = None

    status_unchanged = current_status == target_status
    delivery_unchanged = not _delivery_should_advance(
        current_delivery_str,
        delivery_status,
    )
    if status_unchanged and delivery_unchanged:
        return False

    merged_payload = {**payload_dict, "delivery_status": delivery_status}
    update_body: dict[str, Any] = {"payload": merged_payload}
    if current_status != target_status:
        update_body["status"] = target_status

    client.table(OUTBOX_TABLE).update(update_body).eq("id", row_id).execute()
    return True


def _parse_row_timestamp(row: dict[str, Any], key: str) -> datetime | None:
    raw = row.get(key)
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_notif_prefs(client: Any, recipient_id: str) -> dict[str, Any]:
    response = (
        client.table(PROFILES_TABLE)
        .select("notif_prefs")
        .eq("id", recipient_id)
        .maybe_single()
        .execute()
    )
    row = _extract_data(response)
    if isinstance(row, dict):
        prefs = row.get("notif_prefs")
        if isinstance(prefs, dict):
            return prefs
    return {}


def _maybe_enqueue_lifecycle_fallback(
    client: Any,
    row: dict[str, Any],
    *,
    delivery_status: str,
) -> None:
    """After a WhatsApp delivery failure webhook, queue SMS fallback if appropriate."""
    dedupe_key = str(row.get("dedupe_key", ""))
    event_type, entity_id = split_dedupe_key(dedupe_key)
    if not event_type or not entity_id:
        logger.warning(
            "whatsapp lifecycle fallback skipped: malformed dedupe_key",
            extra={"dedupe_key": dedupe_key, "outbox_id": row.get("id")},
        )
        return

    payload = row.get("payload")
    payload_dict = dict(payload) if isinstance(payload, dict) else {}
    recipient_id = payload_dict.get("recipient_id")
    notif_prefs = _fetch_notif_prefs(client, str(recipient_id)) if recipient_id else {}

    template = row.get("template")
    template_name = template if isinstance(template, str) else None
    if (
        get_template_class(template_name) is TemplateClass.MARKETING
        and not has_any_channel_enabled(notif_prefs)
    ):
        return

    whatsapp_opt_in = payload_dict.get("whatsapp_opt_in", True)
    if not isinstance(whatsapp_opt_in, bool):
        whatsapp_opt_in = True

    sent_at = _parse_row_timestamp(row, "updated_at") or _parse_row_timestamp(row, "created_at")
    context = DeliveryContext(
        channel=FALLBACK_CHANNEL_WHATSAPP,
        whatsapp_opt_in=whatsapp_opt_in,
        delivery_status=delivery_status,
        sent_at=sent_at,
    )
    decision = evaluate_lifecycle_fallback(context, notif_prefs)
    if decision.next_channel is None:
        return

    template = row.get("template")
    try:
        enqueue_fallback_row(
            client,
            event_type=event_type,
            entity_id=entity_id,
            decision=decision,
            template=template if isinstance(template, str) else None,
            payload=payload_dict,
            attempts=int(row.get("attempts", 0)),
        )
    except Exception:
        logger.warning(
            "Failed to enqueue WhatsApp lifecycle SMS fallback",
            exc_info=True,
            extra={"outbox_id": row.get("id"), "dedupe_key": dedupe_key},
        )


def _resolve_profile_by_phone(client: Any, phone: str) -> dict[str, Any] | None:
    for candidate in _normalize_phone_candidates(phone):
        response = (
            client.table(PROFILES_TABLE)
            .select("id,phone,locale,notif_prefs")
            .eq("phone", candidate)
            .maybe_single()
            .execute()
        )
        row = _extract_data(response)
        if isinstance(row, dict):
            return row
    return None


def _load_notifications_messages(locale: str) -> dict[str, Any]:
    base = _notifications_i18n_dir()
    if base is None:
        return {}
    path = base / locale / "notifications.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _resolve_compliance_message(
    locale: str,
    *,
    kind: Literal["stop", "start"],
) -> str:
    key = "stopConfirmation" if kind == "stop" else "startConfirmation"
    for candidate in (locale.strip().lower(), "en"):
        messages = _load_notifications_messages(candidate)
        compliance = messages.get("compliance")
        if isinstance(compliance, dict):
            value = compliance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    msg = f"missing compliance message for {kind}"
    raise KeyError(msg)


def _enqueue_opt_confirmation(
    client: Any,
    *,
    profile: dict[str, Any],
    inbound_message_id: str,
    kind: Literal["stop", "start"],
) -> None:
    profile_id = str(profile.get("id", ""))
    phone = profile.get("phone")
    if not profile_id or not isinstance(phone, str) or not phone.strip():
        return

    locale = profile.get("locale")
    locale_str = locale.strip().lower() if isinstance(locale, str) and locale.strip() else "en"
    try:
        confirmation_body = _resolve_compliance_message(locale_str, kind=kind)
    except KeyError:
        logger.warning(
            "whatsapp opt confirmation skipped: missing i18n copy",
            extra={"profile_id": profile_id, "kind": kind, "locale": locale_str},
        )
        return

    event_type = EVENT_OPT_STOP if kind == "stop" else EVENT_OPT_START
    try:
        enqueue_outbox_row(
            client,
            event_type=event_type,
            entity_id=inbound_message_id,
            channel=CHANNEL_WHATSAPP,
            template=TEMPLATE_COMPLIANCE_CONFIRMATION,
            payload={
                "recipient_id": profile_id,
                "to": phone.strip(),
                "locale": locale_str,
                "confirmation_body": confirmation_body,
            },
        )
    except Exception:
        logger.warning(
            "Failed to enqueue WhatsApp opt confirmation",
            exc_info=True,
            extra={
                "profile_id": profile_id,
                "inbound_message_id": inbound_message_id,
                "kind": kind,
            },
        )


def _write_notif_prefs(client: Any, profile_id: str, prefs: dict[str, bool]) -> None:
    client.table(PROFILES_TABLE).update({"notif_prefs": prefs}).eq("id", profile_id).execute()


def _handle_opt_keyword(
    client: Any,
    *,
    phone: str,
    keyword: str,
    inbound_message_id: str | None = None,
) -> bool:
    normalized = keyword.strip().lower()
    if normalized in _STOP_KEYWORDS:
        prefs = dict(_ALL_CHANNELS_OFF)
        kind: Literal["stop", "start"] = "stop"
    elif normalized in _START_KEYWORDS:
        prefs = dict(_ALL_CHANNELS_ON)
        kind = "start"
    else:
        return False

    profile = _resolve_profile_by_phone(client, phone)
    if profile is None:
        logger.info(
            "whatsapp support inbound",
            extra={
                "event": "unknown_sender",
                "from_phone": phone,
                "keyword": normalized,
            },
        )
        return True

    _write_notif_prefs(client, str(profile["id"]), prefs)
    if inbound_message_id:
        _enqueue_opt_confirmation(
            client,
            profile=profile,
            inbound_message_id=inbound_message_id,
            kind=kind,
        )
    logger.info(
        "whatsapp opt keyword applied",
        extra={
            "event": "opt_keyword",
            "profile_id": str(profile["id"]),
            "keyword": normalized,
            "notif_prefs": prefs,
        },
    )
    return True


def _log_unknown_inbound(*, phone: str, message: dict[str, Any]) -> None:
    body: str | None = None
    text = message.get("text")
    if isinstance(text, dict):
        raw_body = text.get("body")
        if isinstance(raw_body, str):
            body = raw_body[:500]
    logger.info(
        "whatsapp support inbound",
        extra={
            "event": "unknown_inbound",
            "from_phone": phone,
            "message_type": message.get("type"),
            "body": body,
            "message_id": message.get("id"),
        },
    )


def _process_statuses(client: Any, statuses: list[Any]) -> None:
    for item in statuses:
        if not isinstance(item, dict):
            continue
        message_id = item.get("id")
        status = item.get("status")
        if not isinstance(message_id, str) or not isinstance(status, str):
            continue
        row = _find_outbox_by_message_id(client, message_id)
        if row is None:
            logger.warning(
                "whatsapp status for unknown outbox message",
                extra={"whatsapp_message_id": message_id, "status": status},
            )
            continue
        updated = _apply_status_update(client, row, status)
        normalized = status.strip().lower()
        if normalized in {"failed", "undelivered"} and updated:
            mapped = _map_whatsapp_status(status)
            if mapped is not None:
                _, delivery_status = mapped
                _maybe_enqueue_lifecycle_fallback(
                    client,
                    row,
                    delivery_status=delivery_status,
                )


def _process_messages(client: Any, messages: list[Any]) -> None:
    for item in messages:
        if not isinstance(item, dict):
            continue
        sender = item.get("from")
        if not isinstance(sender, str):
            _log_unknown_inbound(phone="unknown", message=item)
            continue

        text = item.get("text")
        body = text.get("body") if isinstance(text, dict) else None
        inbound_message_id = item.get("id")
        message_id = inbound_message_id if isinstance(inbound_message_id, str) else None
        if isinstance(body, str) and _handle_opt_keyword(
            client,
            phone=sender,
            keyword=body,
            inbound_message_id=message_id,
        ):
            continue

        _log_unknown_inbound(phone=sender, message=item)


def _process_webhook_payload(client: Any, payload: dict[str, Any]) -> None:
    if payload.get("object") != "whatsapp_business_account":
        return
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            statuses = value.get("statuses")
            if isinstance(statuses, list):
                _process_statuses(client, statuses)
            messages = value.get("messages")
            if isinstance(messages, list):
                _process_messages(client, messages)


@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta webhook subscription verification (challenge echo)."""
    expected = _verify_token()
    if (
        hub_mode == "subscribe"
        and hub_verify_token
        and expected
        and hub_verify_token == expected
        and hub_challenge is not None
    ):
        return PlainTextResponse(content=hub_challenge)
    raise AppError(
        code="forbidden",
        message="WhatsApp webhook verification failed",
        http_status=403,
    )


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    supabase: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, str]:
    """Inbound WhatsApp events: delivery status + STOP/START opt keywords."""
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    secret = _app_secret()
    if not verify_hub_signature(
        raw_body=raw_body,
        signature_header=signature,
        app_secret=secret,
    ):
        raise AppError(
            code="forbidden",
            message="Invalid WhatsApp webhook signature",
            http_status=403,
        )

    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            code="validation_error",
            message="Invalid WhatsApp webhook JSON body",
            http_status=422,
        ) from exc

    if isinstance(parsed, dict):
        _process_webhook_payload(supabase.client, parsed)

    return {"status": "ok"}
