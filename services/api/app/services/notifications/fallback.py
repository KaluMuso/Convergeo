from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from app.services.notifications.adapters.base import ChannelAdapter, FailureKind
from app.services.notifications.dedupe import enqueue_outbox_row

logger = logging.getLogger(__name__)

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_SMS = "sms"
CHANNEL_EMAIL = "email"
DEFAULT_CHANNEL_ORDER: tuple[str, ...] = (CHANNEL_WHATSAPP, CHANNEL_SMS, CHANNEL_EMAIL)
UNDELIVERED_FALLBACK_SECONDS = 120


class FallbackReason(StrEnum):
    PRIMARY = "primary"
    PREF_OVERRIDE = "pref_override"
    WHATSAPP_NO_OPT_IN = "whatsapp_no_opt_in"
    WHATSAPP_FAILED = "whatsapp_failed"
    WHATSAPP_UNDELIVERED_2MIN = "whatsapp_undelivered_2min"
    SMS_FAILED = "sms_failed"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    """Lifecycle delivery state for fallback evaluation."""

    channel: str
    whatsapp_opt_in: bool = True
    delivery_status: str | None = None
    sent_at: datetime | None = None
    send_failed: bool = False
    failure_kind: FailureKind | None = None


@dataclass(frozen=True, slots=True)
class FallbackDecision:
    next_channel: str | None
    reason: FallbackReason
    detail: str
    from_channel: str | None = None


def channel_enabled(channel: str, notif_prefs: dict[str, Any]) -> bool:
    value = notif_prefs.get(channel)
    if value is None:
        return True
    return bool(value)


def whatsapp_attempt_allowed(
    notif_prefs: dict[str, Any],
    *,
    whatsapp_opt_in: bool = True,
) -> bool:
    if not whatsapp_opt_in:
        return False
    return channel_enabled(CHANNEL_WHATSAPP, notif_prefs)


def resolve_primary_channel(
    notif_prefs: dict[str, Any] | None,
    *,
    whatsapp_opt_in: bool = True,
) -> FallbackDecision:
    """Pick the first enabled channel honoring prefs (SMS-only skips WhatsApp)."""
    prefs = notif_prefs or {}

    if not whatsapp_attempt_allowed(prefs, whatsapp_opt_in=whatsapp_opt_in):
        for channel in (CHANNEL_SMS, CHANNEL_EMAIL):
            if channel_enabled(channel, prefs):
                reason = (
                    FallbackReason.WHATSAPP_NO_OPT_IN
                    if not whatsapp_opt_in
                    else FallbackReason.PREF_OVERRIDE
                )
                detail = (
                    "whatsapp skipped: no opt-in"
                    if not whatsapp_opt_in
                    else "whatsapp disabled by user prefs"
                )
                return FallbackDecision(
                    next_channel=channel,
                    reason=reason,
                    detail=detail,
                    from_channel=CHANNEL_WHATSAPP,
                )

    for channel in DEFAULT_CHANNEL_ORDER:
        if channel_enabled(channel, prefs):
            reason = (
                FallbackReason.PRIMARY
                if channel == CHANNEL_WHATSAPP
                else FallbackReason.PREF_OVERRIDE
            )
            detail = f"primary channel {channel}"
            if channel != CHANNEL_WHATSAPP:
                detail = f"prefs selected {channel} as first enabled channel"
            return FallbackDecision(
                next_channel=channel,
                reason=reason,
                detail=detail,
            )

    return FallbackDecision(
        next_channel=CHANNEL_EMAIL,
        reason=FallbackReason.EXHAUSTED,
        detail="all channels disabled in prefs; defaulting to email",
    )


def undelivered_sla_elapsed(sent_at: datetime | None, *, now: datetime) -> bool:
    if sent_at is None:
        return False
    sent = sent_at if sent_at.tzinfo is not None else sent_at.replace(tzinfo=UTC)
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return (current - sent) >= timedelta(seconds=UNDELIVERED_FALLBACK_SECONDS)


def resolve_fallback_channel(
    context: DeliveryContext,
    notif_prefs: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> FallbackDecision:
    """Resolve the next channel after WhatsApp/SMS failure or undelivered SLA."""
    prefs = notif_prefs or {}
    current = now or datetime.now(UTC)

    if context.channel == CHANNEL_WHATSAPP:
        if not whatsapp_attempt_allowed(prefs, whatsapp_opt_in=context.whatsapp_opt_in):
            decision = FallbackDecision(
                next_channel=CHANNEL_SMS if channel_enabled(CHANNEL_SMS, prefs) else None,
                reason=FallbackReason.WHATSAPP_NO_OPT_IN,
                detail="whatsapp skipped: no opt-in",
                from_channel=CHANNEL_WHATSAPP,
            )
            if decision.next_channel is None and channel_enabled(CHANNEL_EMAIL, prefs):
                return FallbackDecision(
                    next_channel=CHANNEL_EMAIL,
                    reason=FallbackReason.WHATSAPP_NO_OPT_IN,
                    detail="whatsapp skipped: no opt-in; sms disabled",
                    from_channel=CHANNEL_WHATSAPP,
                )
            return _finalize_exhausted(decision, prefs)

        if context.send_failed or context.failure_kind is not None:
            if channel_enabled(CHANNEL_SMS, prefs):
                return FallbackDecision(
                    next_channel=CHANNEL_SMS,
                    reason=FallbackReason.WHATSAPP_FAILED,
                    detail="whatsapp send failed",
                    from_channel=CHANNEL_WHATSAPP,
                )
            if channel_enabled(CHANNEL_EMAIL, prefs):
                return FallbackDecision(
                    next_channel=CHANNEL_EMAIL,
                    reason=FallbackReason.WHATSAPP_FAILED,
                    detail="whatsapp failed; sms disabled",
                    from_channel=CHANNEL_WHATSAPP,
                )
            return FallbackDecision(
                next_channel=None,
                reason=FallbackReason.EXHAUSTED,
                detail="whatsapp failed; no fallback channels enabled",
                from_channel=CHANNEL_WHATSAPP,
            )

        status = (context.delivery_status or "").lower()
        if status in {"delivered", "read"}:
            return FallbackDecision(
                next_channel=None,
                reason=FallbackReason.PRIMARY,
                detail="whatsapp delivered",
                from_channel=CHANNEL_WHATSAPP,
            )

        if status in {"failed", "undelivered"} or undelivered_sla_elapsed(
            context.sent_at, now=current
        ):
            if channel_enabled(CHANNEL_SMS, prefs):
                reason = (
                    FallbackReason.WHATSAPP_UNDELIVERED_2MIN
                    if undelivered_sla_elapsed(context.sent_at, now=current)
                    else FallbackReason.WHATSAPP_FAILED
                )
                detail = (
                    "whatsapp undelivered after 2min SLA"
                    if reason is FallbackReason.WHATSAPP_UNDELIVERED_2MIN
                    else f"whatsapp delivery status={status or 'unknown'}"
                )
                return FallbackDecision(
                    next_channel=CHANNEL_SMS,
                    reason=reason,
                    detail=detail,
                    from_channel=CHANNEL_WHATSAPP,
                )
            if channel_enabled(CHANNEL_EMAIL, prefs):
                return FallbackDecision(
                    next_channel=CHANNEL_EMAIL,
                    reason=FallbackReason.WHATSAPP_UNDELIVERED_2MIN,
                    detail="whatsapp undelivered; sms disabled",
                    from_channel=CHANNEL_WHATSAPP,
                )

        return FallbackDecision(
            next_channel=None,
            reason=FallbackReason.PRIMARY,
            detail="whatsapp pending delivery",
            from_channel=CHANNEL_WHATSAPP,
        )

    if context.channel == CHANNEL_SMS:
        if context.send_failed or context.failure_kind is not None:
            if channel_enabled(CHANNEL_EMAIL, prefs):
                return FallbackDecision(
                    next_channel=CHANNEL_EMAIL,
                    reason=FallbackReason.SMS_FAILED,
                    detail="sms send failed",
                    from_channel=CHANNEL_SMS,
                )
            return FallbackDecision(
                next_channel=None,
                reason=FallbackReason.EXHAUSTED,
                detail="sms failed; email disabled",
                from_channel=CHANNEL_SMS,
            )

    return FallbackDecision(
        next_channel=None,
        reason=FallbackReason.EXHAUSTED,
        detail="no further fallback",
        from_channel=context.channel,
    )


def _finalize_exhausted(decision: FallbackDecision, prefs: dict[str, Any]) -> FallbackDecision:
    if decision.next_channel is not None:
        return decision
    if channel_enabled(CHANNEL_EMAIL, prefs):
        return FallbackDecision(
            next_channel=CHANNEL_EMAIL,
            reason=decision.reason,
            detail=f"{decision.detail}; sms disabled",
            from_channel=decision.from_channel,
        )
    return FallbackDecision(
        next_channel=None,
        reason=FallbackReason.EXHAUSTED,
        detail=f"{decision.detail}; no channels enabled",
        from_channel=decision.from_channel,
    )


def get_channel_adapter(
    adapters: Mapping[str, ChannelAdapter],
    channel: str,
) -> ChannelAdapter | None:
    """Resolve adapter by channel name (no direct whatsapp module import)."""
    return adapters.get(channel)


def build_fallback_audit(
    decision: FallbackDecision,
    *,
    attempts: int,
) -> dict[str, Any]:
    """Attach fallback decision to outbox payload attempts audit (no schema change)."""
    return {
        "fallback": {
            "from_channel": decision.from_channel,
            "to_channel": decision.next_channel,
            "reason": decision.reason.value,
            "detail": decision.detail,
            "attempts": attempts,
            "logged_at": datetime.now(UTC).isoformat(),
        }
    }


def log_fallback_decision(
    decision: FallbackDecision,
    *,
    outbox_id: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    attempts: int = 0,
) -> None:
    """Structured log for why a fallback channel was chosen."""
    logger.info(
        "notification fallback decision",
        extra={
            "outbox_id": outbox_id,
            "entity_id": entity_id,
            "event_type": event_type,
            "from_channel": decision.from_channel,
            "to_channel": decision.next_channel,
            "reason": decision.reason.value,
            "detail": decision.detail,
            "attempts": attempts,
        },
    )


def enqueue_fallback_row(
    client: Any,
    *,
    event_type: str,
    entity_id: str,
    decision: FallbackDecision,
    template: str | None,
    payload: dict[str, Any],
    attempts: int = 0,
) -> dict[str, Any] | None:
    """Enqueue the fallback channel outbox row after logging the decision."""
    if decision.next_channel is None:
        return None

    log_fallback_decision(
        decision,
        entity_id=entity_id,
        event_type=event_type,
        attempts=attempts,
    )

    merged_payload = {
        **payload,
        **build_fallback_audit(decision, attempts=attempts),
    }
    return enqueue_outbox_row(
        client,
        event_type=event_type,
        entity_id=entity_id,
        channel=decision.next_channel,
        template=template,
        payload=merged_payload,
    )


def evaluate_lifecycle_fallback(
    context: DeliveryContext,
    notif_prefs: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> FallbackDecision:
    """Entry point: primary channel for new messages or fallback for in-flight."""
    if context.send_failed or context.delivery_status not in {None, "", "pending", "sent"}:
        return resolve_fallback_channel(context, notif_prefs, now=now)

    if context.channel == CHANNEL_WHATSAPP and context.sent_at is not None:
        return resolve_fallback_channel(context, notif_prefs, now=now)

    if context.channel == CHANNEL_WHATSAPP and not whatsapp_attempt_allowed(
        notif_prefs or {},
        whatsapp_opt_in=context.whatsapp_opt_in,
    ):
        return resolve_primary_channel(
            notif_prefs,
            whatsapp_opt_in=context.whatsapp_opt_in,
        )

    return resolve_primary_channel(notif_prefs, whatsapp_opt_in=context.whatsapp_opt_in)
