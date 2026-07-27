"""M18-P01 — intake session service (D35).

Two responsibilities, both security-critical:

1. :func:`resolve_verified_sender` — decide whether an inbound MSISDN belongs to
   an eligible, enrolled vendor, **without disclosing anything** when it does
   not. "No such number" and "number exists but the vendor is suspended" return
   the *same* value and log the *same* way. A caller cannot distinguish them,
   so the intake number can never be used to probe whether a business is on the
   platform.

2. :func:`record_inbound` — idempotently attach an inbound message to a session.
   A replayed provider message id is a no-op that returns the existing session:
   never a second session, never a second draft.

This module sends nothing. The lane is strictly inbound-only (corrected D35).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from app.errors import AppError
from app.services.intake import state_machine

logger = logging.getLogger(__name__)

BINDINGS_TABLE: Final = "intake_vendor_bindings"
SESSIONS_TABLE: Final = "intake_sessions"
MESSAGES_TABLE: Final = "intake_messages"
VENDORS_TABLE: Final = "vendors"

# Zambian mobile MSISDN, E.164 digits without the plus.
MSISDN_PATTERN: Final = re.compile(r"^260[79][0-9]{8}$")

# D35 §4.4: active storefront AND at least KYC tier 1.
MIN_KYC_TIER: Final = 1
ACTIVE_VENDOR_STATUS: Final = "active"

MESSAGE_KINDS: Final[frozenset[str]] = frozenset({"text", "image", "mixed", "unsupported"})


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class VerifiedSender:
    """An eligible, enrolled vendor. Only ever constructed after every check."""

    vendor_id: str
    binding_id: str


# The single "not eligible" answer. Deliberately carries NO reason: unknown
# number, opted-out binding, suspended vendor, and insufficient KYC tier all
# resolve to this identical value so no caller can leak the difference.
NOT_ELIGIBLE: Final = None


def normalise_msisdn(raw: str | None) -> str | None:
    """Normalise to E.164 digits-no-plus, or ``None`` if it is not a ZM mobile."""
    if not raw:
        return None
    digits = "".join(char for char in raw if char.isdigit())
    # Tolerate the common local forms: 0977..., 260977..., +260977...
    if digits.startswith("0") and len(digits) == 10:
        digits = "260" + digits[1:]
    if not MSISDN_PATTERN.match(digits):
        return None
    return digits


def _table(service_client: ServiceRoleClient, name: str) -> Any:
    return service_client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _mask(msisdn: str) -> str:
    """Log-safe MSISDN: last three digits only (D35 redaction)."""
    return f"***{msisdn[-3:]}" if len(msisdn) >= 3 else "***"


def resolve_verified_sender(
    service_client: ServiceRoleClient, raw_msisdn: str | None
) -> VerifiedSender | None:
    """Return the enrolled vendor for ``raw_msisdn``, or ``None``.

    ``None`` means *not eligible* and nothing more. It is returned identically
    for an unknown number, an opted-out binding, a suspended vendor, and an
    under-tier vendor — and the log line is identical too. Callers must not
    branch on the reason, because there is none to branch on.
    """
    msisdn = normalise_msisdn(raw_msisdn)
    if msisdn is None:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    try:
        response = (
            _table(service_client, BINDINGS_TABLE)
            .select("id, vendor_id")
            .eq("msisdn", msisdn)
            .is_("opted_out_at", None)
            .execute()
        )
    except Exception:
        # Fail closed, and say no more than for any other ineligible sender.
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    bindings = _rows(response)
    # The unique partial index makes >1 impossible; if it somehow happens,
    # ambiguity is treated as ineligible rather than resolved by guessing.
    if len(bindings) != 1:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    binding = bindings[0]
    vendor_id = str(binding.get("vendor_id") or "")
    binding_id = str(binding.get("id") or "")
    if not vendor_id or not binding_id:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    try:
        vendor_response = (
            _table(service_client, VENDORS_TABLE)
            .select("id, status, kyc_tier")
            .eq("id", vendor_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    vendors = _rows(vendor_response)
    if not vendors:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    vendor = vendors[0]
    if str(vendor.get("status")) != ACTIVE_VENDOR_STATUS:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    try:
        kyc_tier = int(vendor.get("kyc_tier") or 0)
    except (TypeError, ValueError):
        kyc_tier = 0
    if kyc_tier < MIN_KYC_TIER:
        logger.info("intake sender not eligible")
        return NOT_ELIGIBLE

    logger.info("intake sender eligible", extra={"msisdn": _mask(msisdn)})
    return VerifiedSender(vendor_id=vendor_id, binding_id=binding_id)


def _open_session(
    service_client: ServiceRoleClient, sender: VerifiedSender
) -> dict[str, Any] | None:
    """Return the vendor's in-flight session, if one is still collecting."""
    response = (
        _table(service_client, SESSIONS_TABLE)
        .select("*")
        .eq("vendor_id", sender.vendor_id)
        .in_("status", [state_machine.COLLECTING, state_machine.NEEDS_DETAILS])
        .order("last_activity_at", desc=True)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def _existing_message(
    service_client: ServiceRoleClient, provider_message_id: str
) -> dict[str, Any] | None:
    response = (
        _table(service_client, MESSAGES_TABLE)
        .select("id, session_id")
        .eq("provider_message_id", provider_message_id)
        .maybe_single()
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def record_inbound(
    service_client: ServiceRoleClient,
    *,
    sender: VerifiedSender,
    provider_message_id: str,
    kind: str = "text",
    raw_excerpt: str | None = None,
) -> dict[str, Any]:
    """Attach an inbound message to the vendor's session, idempotently.

    A replayed ``provider_message_id`` returns the existing session unchanged —
    no second session, no second message row, no second draft.
    """
    if kind not in MESSAGE_KINDS:
        kind = "unsupported"

    existing = _existing_message(service_client, provider_message_id)
    if existing is not None:
        # Replay. Return what we already have and change nothing.
        return state_machine.load_session(service_client, str(existing["session_id"]))

    session = _open_session(service_client, sender)
    if session is None:
        created = (
            _table(service_client, SESSIONS_TABLE)
            .insert(
                {
                    "vendor_id": sender.vendor_id,
                    "binding_id": sender.binding_id,
                    "status": state_machine.COLLECTING,
                }
            )
            .execute()
        )
        rows = _rows(created)
        session = rows[0] if rows else {}

    session_id = str(session.get("id") or "")

    _table(service_client, MESSAGES_TABLE).insert(
        {
            "session_id": session_id,
            "provider_message_id": provider_message_id,
            "kind": kind,
            # Minimised: an excerpt for extraction, purged by the M18-P07 sweep.
            "raw_excerpt": raw_excerpt,
        }
    ).execute()

    state_machine.record_ingestion(
        service_client,
        disposition=state_machine.DISPOSITION_DRAFT_CREATED,
        vendor_id=sender.vendor_id,
        session_id=session_id,
        provider_event_id=provider_message_id,
        message_kind=kind,
    )
    return session


def enroll(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
    raw_msisdn: str,
    consent_source: str = "vendor_app",
) -> dict[str, Any]:
    """Bind a vendor to an intake MSISDN with explicit, timestamped consent."""
    msisdn = normalise_msisdn(raw_msisdn)
    if msisdn is None:
        raise AppError(
            code="invalid_msisdn",
            message="Not a valid Zambian mobile number",
            http_status=400,
        )

    response = (
        _table(service_client, BINDINGS_TABLE)
        .insert(
            {
                "vendor_id": vendor_id,
                "msisdn": msisdn,
                "consent_source": consent_source,
            }
        )
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else {}


def disenroll(service_client: ServiceRoleClient, *, binding_id: str) -> None:
    """Opt a vendor out. The row is retained (audit); the binding goes inactive.

    Reversible by design: re-enrolling creates a new active binding, and the
    unique partial index keeps at most one active binding per number.
    """
    _table(service_client, BINDINGS_TABLE).update(
        {"opted_out_at": datetime.now(UTC).isoformat()}
    ).eq("id", binding_id).is_("opted_out_at", None).execute()
