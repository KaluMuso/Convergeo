from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.services.notifications.adapters.base import (
    ChannelAdapter,
    FailureKind,
    OutboxMessage,
)
from app.services.notifications.dedupe import (
    DEFAULT_CHANNEL_ORDER,
    is_pending_dispatch,
)

logger = logging.getLogger(__name__)

OUTBOX_TABLE = "notification_outbox"
PROFILES_TABLE = "profiles"
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_BASE_SECONDS = 60
DEFAULT_CHANNEL_PACE_SECONDS: dict[str, float] = {
    "whatsapp": 0.05,
    "sms": 0.05,
    "email": 0.05,
}


class SupabaseService(Protocol):
    @property
    def client(self) -> Any:
        """Underlying Supabase client with table query builders."""
        ...


@dataclass(frozen=True, slots=True)
class DispatchStats:
    processed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0


def compute_backoff_seconds(
    attempts: int,
    *,
    base_seconds: int = DEFAULT_BACKOFF_BASE_SECONDS,
) -> int:
    """Exponential backoff from the attempt count (1-indexed after increment)."""
    exponent = max(attempts - 1, 0)
    return int(base_seconds * (2**exponent))


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _channel_enabled(channel: str, notif_prefs: dict[str, Any]) -> bool:
    value = notif_prefs.get(channel)
    if value is None:
        return True
    return bool(value)


def resolve_channel(
    requested_channel: str,
    notif_prefs: dict[str, Any] | None,
) -> str:
    """Honor recipient prefs; fall back through whatsapp → sms → email when absent."""
    prefs = notif_prefs or {}
    order = DEFAULT_CHANNEL_ORDER

    if requested_channel in order and _channel_enabled(requested_channel, prefs):
        return requested_channel

    for channel in order:
        if _channel_enabled(channel, prefs):
            return channel

    return requested_channel


class NotificationDispatcher:
    def __init__(
        self,
        supabase: SupabaseService,
        adapters: dict[str, ChannelAdapter],
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base_seconds: int = DEFAULT_BACKOFF_BASE_SECONDS,
        channel_pace_seconds: dict[str, float] | None = None,
    ) -> None:
        self._supabase = supabase
        self._adapters = adapters
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._channel_pace_seconds = channel_pace_seconds or DEFAULT_CHANNEL_PACE_SECONDS
        self._last_send_at: dict[str, datetime] = {}

    @property
    def client(self) -> Any:
        return self._supabase.client

    def fetch_pending_rows(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Poll pending rows ready for dispatch (uses status + next_retry_at index)."""
        current = now or datetime.now(UTC)
        now_iso = current.isoformat()
        response = (
            self.client.table(OUTBOX_TABLE)
            .select("*")
            .eq("status", "pending")
            .or_(f"next_retry_at.is.null,next_retry_at.lte.{now_iso}")
            .order("created_at")
            .limit(self._batch_size)
            .execute()
        )
        data = response.data
        if not isinstance(data, list):
            return []
        return [row for row in data if isinstance(row, dict)]

    def fetch_notif_prefs(self, recipient_id: str) -> dict[str, Any]:
        try:
            response = (
                self.client.table(PROFILES_TABLE)
                .select("notif_prefs")
                .eq("id", recipient_id)
                .maybe_single()
                .execute()
            )
            row = response.data
            if isinstance(row, dict):
                prefs = row.get("notif_prefs")
                if isinstance(prefs, dict):
                    return prefs
        except Exception:
            logger.debug("Failed to load notif_prefs for recipient", exc_info=True)
        return {}

    def fetch_recipient(self, recipient_id: str) -> dict[str, Any]:
        """Load the recipient's contact + prefs (phone, locale, notif_prefs)."""
        try:
            response = (
                self.client.table(PROFILES_TABLE)
                .select("phone, locale, notif_prefs")
                .eq("id", recipient_id)
                .maybe_single()
                .execute()
            )
            row = response.data
            if isinstance(row, dict):
                return row
        except Exception:
            logger.debug("Failed to load recipient profile", exc_info=True)
        return {}

    def fetch_row(self, row_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table(OUTBOX_TABLE).select("*").eq("id", row_id).maybe_single().execute()
        )
        row = response.data
        return row if isinstance(row, dict) else None

    def mark_sent(self, row_id: str) -> bool:
        response = (
            self.client.table(OUTBOX_TABLE)
            .update({"status": "sent"})
            .eq("id", row_id)
            .eq("status", "pending")
            .execute()
        )
        data = response.data
        if isinstance(data, list):
            return len(data) > 0
        return bool(data)

    def mark_failed(self, row_id: str, *, attempts: int) -> None:
        self.client.table(OUTBOX_TABLE).update(
            {
                "status": "failed",
                "attempts": attempts,
                "next_retry_at": None,
            }
        ).eq("id", row_id).execute()

    def schedule_retry(self, row_id: str, *, attempts: int, next_retry_at: datetime) -> None:
        self.client.table(OUTBOX_TABLE).update(
            {
                "status": "pending",
                "attempts": attempts,
                "next_retry_at": next_retry_at.isoformat(),
            }
        ).eq("id", row_id).execute()

    async def run_batch(self, *, now: datetime | None = None) -> DispatchStats:
        current = now or datetime.now(UTC)
        stats = DispatchStats()
        rows = self.fetch_pending_rows(now=current)

        for row in rows:
            outcome = await self._process_row(row, now=current)
            stats = DispatchStats(
                processed=stats.processed + 1,
                sent=stats.sent + (1 if outcome == "sent" else 0),
                failed=stats.failed + (1 if outcome == "failed" else 0),
                skipped=stats.skipped + (1 if outcome == "skipped" else 0),
                retried=stats.retried + (1 if outcome == "retried" else 0),
            )

        return stats

    async def _process_row(self, row: dict[str, Any], *, now: datetime) -> str:
        row_id = str(row.get("id", ""))
        if not row_id:
            return "skipped"

        fresh = self.fetch_row(row_id)
        if fresh is None or not is_pending_dispatch(fresh):
            return "skipped"

        next_retry_at = _parse_timestamp(fresh.get("next_retry_at"))
        if next_retry_at is not None and next_retry_at > now:
            return "skipped"

        payload = fresh.get("payload")
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        recipient_id = payload_dict.get("recipient_id")
        recipient = self.fetch_recipient(str(recipient_id)) if recipient_id is not None else {}
        notif_prefs_raw = recipient.get("notif_prefs")
        notif_prefs = notif_prefs_raw if isinstance(notif_prefs_raw, dict) else {}

        # Inject the recipient's destination contact so the adapters/templates can
        # address them: WhatsApp render needs `to` (E.164), SMS needs `phone`,
        # WhatsApp locale selection reads `locale`. Enqueue-time payload wins if set.
        phone = recipient.get("phone")
        if isinstance(phone, str) and phone:
            payload_dict.setdefault("to", phone)
            payload_dict.setdefault("phone", phone)
        locale = recipient.get("locale")
        if isinstance(locale, str) and locale:
            payload_dict.setdefault("locale", locale)

        requested_channel = str(fresh.get("channel", "whatsapp"))
        channel = resolve_channel(requested_channel, notif_prefs)
        adapter = self._adapters.get(channel)
        if adapter is None:
            logger.error("No adapter registered for channel", extra={"channel": channel})
            self.mark_failed(row_id, attempts=int(fresh.get("attempts", 0)) + 1)
            return "failed"

        await self._apply_channel_pace(channel, now=now)

        message = OutboxMessage(
            id=row_id,
            dedupe_key=str(fresh.get("dedupe_key", "")),
            channel=channel,
            template=fresh.get("template") if isinstance(fresh.get("template"), str) else None,
            payload=payload_dict,
        )

        result = await adapter.send(message)
        if result.success:
            if self.mark_sent(row_id):
                return "sent"
            return "skipped"

        attempts = int(fresh.get("attempts", 0)) + 1
        failure_kind = result.failure_kind or FailureKind.RETRYABLE

        if failure_kind is FailureKind.PERMANENT or attempts >= self._max_attempts:
            self.mark_failed(row_id, attempts=attempts)
            return "failed"

        delay_seconds = compute_backoff_seconds(
            attempts,
            base_seconds=self._backoff_base_seconds,
        )
        self.schedule_retry(
            row_id,
            attempts=attempts,
            next_retry_at=now + timedelta(seconds=delay_seconds),
        )
        return "retried"

    async def _apply_channel_pace(self, channel: str, *, now: datetime) -> None:
        pace = self._channel_pace_seconds.get(channel, 0.0)
        if pace <= 0:
            return

        last_sent = self._last_send_at.get(channel)
        if last_sent is not None:
            elapsed = (now - last_sent).total_seconds()
            if elapsed < pace:
                await asyncio.sleep(pace - elapsed)

        self._last_send_at[channel] = datetime.now(UTC)


async def run_dispatch_batch(
    supabase: SupabaseService,
    adapters: dict[str, ChannelAdapter],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DispatchStats:
    dispatcher = NotificationDispatcher(
        supabase,
        adapters,
        batch_size=batch_size,
    )
    return await dispatcher.run_batch()
