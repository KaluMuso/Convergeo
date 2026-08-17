"""Integer USD/ZMW rate loading, publishing, and order snapshots.

Rates are stored as micro-ZMW per USD. Checkout copies the selected row into
``orders.fx_snapshot``; the DB trigger then freezes that JSON for the life of
the order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.errors import AppError
from app.services.listings.pricing import usd_microdollars_to_zmw_ngwee

DEFAULT_MAX_AGE_HOURS = 24
MAX_VENDOR_MARGIN_BPS = 5_000


@dataclass(frozen=True, slots=True)
class FxSnapshot:
    rate_id: str
    rate_zmw_per_usd_micros: int
    vendor_margin_bps: int
    source: str
    source_reference: str | None
    effective_at: datetime
    expires_at: datetime
    stale: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "quote_currency": "ZMW",
            "base_currency": "USD",
            "conversion_applied": True,
            "rate_id": self.rate_id,
            "rate_zmw_per_usd_micros": self.rate_zmw_per_usd_micros,
            "vendor_margin_bps": self.vendor_margin_bps,
            "source": self.source,
            "source_reference": self.source_reference,
            "effective_at": self.effective_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "stale": self.stale,
        }


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _max_age_hours(client: Any) -> int:
    try:
        response = (
            client.table("platform_config")
            .select("value")
            .eq("key", "fx_rate_max_age_hours")
            .maybe_single()
            .execute()
        )
    except Exception:  # pragma: no cover - missing table must not break checkout
        return DEFAULT_MAX_AGE_HOURS
    row = response.data if isinstance(getattr(response, "data", None), dict) else None
    if row is None:
        return DEFAULT_MAX_AGE_HOURS
    raw = row.get("value")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return DEFAULT_MAX_AGE_HOURS


def load_current_usd_zmw_rate(client: Any, *, now: datetime | None = None) -> FxSnapshot | None:
    """Return the current (not superseded) USD/ZMW row, or None if unpublished."""
    clock = now or datetime.now(UTC)
    response = (
        client.table("fx_rates")
        .select(
            "id, rate_zmw_per_usd_micros, vendor_margin_bps, source, source_reference, "
            "effective_at, expires_at"
        )
        .is_("superseded_at", "null")
        .eq("base_currency", "USD")
        .eq("quote_currency", "ZMW")
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    row = rows[0]
    rate_id = row.get("id")
    rate = row.get("rate_zmw_per_usd_micros")
    margin = row.get("vendor_margin_bps")
    source = row.get("source")
    effective_at = _parse_dt(row.get("effective_at"))
    expires_at = _parse_dt(row.get("expires_at"))
    if not isinstance(rate_id, str) or not isinstance(rate, int) or rate <= 0:
        return None
    if not isinstance(margin, int) or not isinstance(source, str) or not source.strip():
        return None
    if effective_at is None or expires_at is None:
        return None
    max_age = timedelta(hours=_max_age_hours(client))
    stale = clock >= expires_at or clock < effective_at or (clock - effective_at) > max_age
    source_ref = row.get("source_reference")
    return FxSnapshot(
        rate_id=rate_id,
        rate_zmw_per_usd_micros=rate,
        vendor_margin_bps=margin,
        source=source.strip(),
        source_reference=str(source_ref) if isinstance(source_ref, str) else None,
        effective_at=effective_at,
        expires_at=expires_at,
        stale=stale,
    )


def require_fresh_usd_zmw_rate(client: Any, *, now: datetime | None = None) -> FxSnapshot:
    snapshot = load_current_usd_zmw_rate(client, now=now)
    if snapshot is None:
        raise AppError(
            code="fx.rate_unavailable",
            message="No current USD/ZMW rate is published",
            http_status=409,
            details={"message_key": "checkout.fxUnavailable"},
        )
    if snapshot.stale:
        raise AppError(
            code="fx.rate_stale",
            message="The published USD/ZMW rate has expired",
            http_status=409,
            details={
                "message_key": "checkout.fxStale",
                "rate_id": snapshot.rate_id,
                "expires_at": snapshot.expires_at.isoformat(),
            },
        )
    return snapshot


def build_order_fx_snapshot(
    *,
    used_usd: bool,
    rate: FxSnapshot | None,
) -> dict[str, Any]:
    """Immutable order payload. ZMW-only checkouts record that no conversion ran."""
    if not used_usd:
        return {
            "quote_currency": "ZMW",
            "conversion_applied": False,
        }
    if rate is None:
        raise AppError(
            code="fx.rate_unavailable",
            message="USD listings require a published FX rate",
            http_status=409,
            details={"message_key": "checkout.fxUnavailable"},
        )
    return rate.to_json()


def convert_usd_listing_price_ngwee(
    *,
    usd_microdollars: int,
    rate: FxSnapshot,
) -> int:
    return usd_microdollars_to_zmw_ngwee(
        usd_microdollars=usd_microdollars,
        rate_zmw_per_usd_micros=rate.rate_zmw_per_usd_micros,
        vendor_margin_bps=rate.vendor_margin_bps,
    )


def publish_usd_zmw_rate(
    client: Any,
    *,
    rate_zmw_per_usd_micros: int,
    vendor_margin_bps: int,
    source: str,
    source_reference: str | None,
    effective_at: datetime,
    expires_at: datetime,
    created_by: str | None,
) -> FxSnapshot:
    if rate_zmw_per_usd_micros <= 0:
        raise AppError(
            code="validation_error",
            message="rate_zmw_per_usd_micros must be positive",
            http_status=422,
            details={"rate_zmw_per_usd_micros": "must be > 0"},
        )
    if not 0 <= vendor_margin_bps <= MAX_VENDOR_MARGIN_BPS:
        raise AppError(
            code="validation_error",
            message="vendor_margin_bps out of bounds",
            http_status=422,
            details={"vendor_margin_bps": f"must be between 0 and {MAX_VENDOR_MARGIN_BPS}"},
        )
    trimmed_source = source.strip()
    if not trimmed_source:
        raise AppError(
            code="validation_error",
            message="source is required",
            http_status=422,
            details={"source": "required"},
        )
    if expires_at <= effective_at:
        raise AppError(
            code="validation_error",
            message="expires_at must be after effective_at",
            http_status=422,
            details={"expires_at": "must be after effective_at"},
        )

    now = datetime.now(UTC)
    current = load_current_usd_zmw_rate(client, now=now)
    if current is not None:
        client.table("fx_rates").update({"superseded_at": now.isoformat()}).eq(
            "id", current.rate_id
        ).is_("superseded_at", "null").execute()

    rate_id = str(uuid4())
    payload: dict[str, Any] = {
        "id": rate_id,
        "base_currency": "USD",
        "quote_currency": "ZMW",
        "rate_zmw_per_usd_micros": rate_zmw_per_usd_micros,
        "vendor_margin_bps": vendor_margin_bps,
        "source": trimmed_source,
        "source_reference": source_reference,
        "effective_at": effective_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "created_by": created_by,
    }
    client.table("fx_rates").insert(payload).execute()
    loaded = load_current_usd_zmw_rate(client, now=now)
    if loaded is None:
        raise AppError(
            code="internal_error",
            message="Failed to publish FX rate",
            http_status=500,
        )
    return loaded


def list_usd_zmw_rates(client: Any, *, limit: int = 25, now: datetime | None = None) -> list[FxSnapshot]:
    """Newest-first USD/ZMW history, including superseded rows."""
    clock = now or datetime.now(UTC)
    response = (
        client.table("fx_rates")
        .select(
            "id, rate_zmw_per_usd_micros, vendor_margin_bps, source, source_reference, "
            "effective_at, expires_at, superseded_at"
        )
        .eq("base_currency", "USD")
        .eq("quote_currency", "ZMW")
        .order("effective_at", desc=True)
        .limit(max(1, min(limit, 100)))
        .execute()
    )
    snapshots: list[FxSnapshot] = []
    max_age = timedelta(hours=_max_age_hours(client))
    for row in _rows(response):
        rate_id = row.get("id")
        rate = row.get("rate_zmw_per_usd_micros")
        margin = row.get("vendor_margin_bps")
        source = row.get("source")
        effective_at = _parse_dt(row.get("effective_at"))
        expires_at = _parse_dt(row.get("expires_at"))
        if not isinstance(rate_id, str) or not isinstance(rate, int) or rate <= 0:
            continue
        if not isinstance(margin, int) or not isinstance(source, str) or not source.strip():
            continue
        if effective_at is None or expires_at is None:
            continue
        superseded = _parse_dt(row.get("superseded_at"))
        stale = (
            superseded is not None
            or clock >= expires_at
            or clock < effective_at
            or (clock - effective_at) > max_age
        )
        source_ref = row.get("source_reference")
        snapshots.append(
            FxSnapshot(
                rate_id=rate_id,
                rate_zmw_per_usd_micros=rate,
                vendor_margin_bps=margin,
                source=source.strip(),
                source_reference=str(source_ref) if isinstance(source_ref, str) else None,
                effective_at=effective_at,
                expires_at=expires_at,
                stale=stale,
            )
        )
    return snapshots
