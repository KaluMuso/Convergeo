"""M17-P08 — monthly video cost accounting and the upload kill switch.

Cloned from ``services/ask/spend.py``'s proven shape rather than forked from it:
same micro-USD integers, same ``platform_config`` cap override, same
month-keyed row, same reversible-and-audited reset. The two guards stay separate
because they bound different budgets — an AI overspend must not pause uploads,
and a video overspend must not silence Ask Vergeo.

Two rules define this module:

1. **No float on a cost path.** Rates are read as ``Decimal`` and immediately
   converted to integer micro-USD. A float here would drift by fractions of a
   cent per clip and by real money over a month, and it is a review-blocking bug
   everywhere else in this codebase for exactly that reason.

2. **The switch pauses uploads, never the feed.** :func:`raise_if_killed` is
   called at the upload seam and nowhere else. Posters, captions, prices, linked
   listings and add-to-cart keep working when it trips — a cost guard that took
   the shoppable surface down would turn a billing event into an outage, and the
   part that makes money is the last thing that should stop.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, Protocol

from app.errors import AppError

logger = logging.getLogger(__name__)

SPEND_TABLE: Final = "clip_spend_monthly"
CONFIG_TABLE: Final = "platform_config"

#: Inside the $50/mo infrastructure ceiling, alongside Ask Vergeo's $15.
DEFAULT_MONTHLY_CAP_USD: Final = 10

MICROS_PER_USD: Final = 1_000_000

#: platform_config keys. Both are overridable without a deploy — the operator
#: actions in docs/ops/clip-cost-runbook.md are all config changes.
CAP_KEY: Final = "clip_monthly_cap_usd"
RATES_KEY: Final = "clip_cost_rates"

#: Fallback unit rates in USD. Deliberately conservative: over-estimating spend
#: trips the guard early, which is recoverable; under-estimating it produces an
#: invoice, which is not.
DEFAULT_RATES: Final[dict[str, str]] = {
    #: per transcoded clip (both renditions + poster)
    "transcode_per_clip": "0.02",
    #: per gigabyte delivered
    "delivery_per_gb": "0.08",
}

_CONFIG_CACHE_TTL_SECONDS: Final = 60.0
_config_cache: dict[str, tuple[float, Any]] = {}
_config_lock = threading.Lock()


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def clear_clip_spend_cache() -> None:
    with _config_lock:
        _config_cache.clear()


def current_month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _read_config(service_client: ServiceRoleClient, key: str) -> Any:
    now = datetime.now(UTC).timestamp()
    with _config_lock:
        cached = _config_cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    parsed: Any = None
    try:
        rows = _rows(
            service_client.client.table(CONFIG_TABLE)
            .select("value")
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        parsed = rows[0].get("value") if rows else None
    except Exception:
        logger.warning("clip spend config read failed for %s", key)

    with _config_lock:
        _config_cache[key] = (now + _CONFIG_CACHE_TTL_SECONDS, parsed)
    return parsed


def monthly_cap_usd_micros(service_client: ServiceRoleClient) -> int:
    raw = _read_config(service_client, CAP_KEY)
    cap_usd = DEFAULT_MONTHLY_CAP_USD
    if isinstance(raw, bool):
        pass
    elif isinstance(raw, (int, float)):
        cap_usd = int(raw)
    elif isinstance(raw, str) and raw.strip().isdigit():
        cap_usd = int(raw.strip())
    return max(0, cap_usd) * MICROS_PER_USD


def unit_rates(service_client: ServiceRoleClient) -> dict[str, Decimal]:
    """Unit costs in USD, as ``Decimal``. Invalid entries fall back, never crash."""
    raw = _read_config(service_client, RATES_KEY)
    rates: dict[str, Decimal] = {
        name: Decimal(value) for name, value in DEFAULT_RATES.items()
    }
    if isinstance(raw, dict):
        for name, value in raw.items():
            try:
                rates[str(name)] = Decimal(str(value))
            except Exception:
                logger.warning("skipping invalid clip cost rate for %s", name)
    return rates


def _usd_to_micros(usd: Decimal) -> int:
    return int((usd * Decimal(MICROS_PER_USD)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def transcode_cost_micros(service_client: ServiceRoleClient, *, clips: int = 1) -> int:
    if clips <= 0:
        return 0
    rate = unit_rates(service_client)["transcode_per_clip"]
    return _usd_to_micros(rate * Decimal(clips))


def delivery_cost_micros(service_client: ServiceRoleClient, *, bytes_served: int) -> int:
    if bytes_served <= 0:
        return 0
    rate = unit_rates(service_client)["delivery_per_gb"]
    gigabytes = Decimal(bytes_served) / Decimal(1_073_741_824)
    return _usd_to_micros(rate * gigabytes)


def _month_row(
    service_client: ServiceRoleClient, month_key: str
) -> dict[str, Any] | None:
    rows = _rows(
        service_client.client.table(SPEND_TABLE)
        .select(
            "month_key, total_usd_micros, clips_transcoded, "
            "bytes_served, killed_at, admin_reset_at"
        )
        .eq("month_key", month_key)
        .maybe_single()
        .execute()
    )
    return rows[0] if rows else None


def current_month_total_micros(
    service_client: ServiceRoleClient, *, month_key: str | None = None
) -> int:
    row = _month_row(service_client, month_key or current_month_key())
    if not row:
        return 0
    value = row.get("total_usd_micros")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return max(0, int(value))
    return 0


def is_killed(
    service_client: ServiceRoleClient, *, month_key: str | None = None
) -> bool:
    """Whether uploads are currently paused for the month.

    A reset that is *newer than* the kill re-opens the month. Comparing the two
    timestamps rather than clearing ``killed_at`` keeps the history: an auditor
    can see that the switch tripped and that an operator reversed it, which a
    destructive reset would erase.
    """
    row = _month_row(service_client, month_key or current_month_key())
    if not row:
        return False
    killed_at = row.get("killed_at")
    if not killed_at:
        return False
    reset_at = row.get("admin_reset_at")
    if reset_at and str(reset_at) >= str(killed_at):
        return False
    return True


def record_spend(
    service_client: ServiceRoleClient,
    *,
    usd_micros: int,
    clips: int = 0,
    bytes_served: int = 0,
    month_key: str | None = None,
) -> int:
    """Add to the month's total and trip the switch if the cap is reached.

    Returns the new total. Uses the ``clip_record_spend`` ``SECURITY DEFINER``
    function so the increment is relative and atomic — a read-then-write would
    lose concurrent transcode callbacks, and losing spend is the one direction a
    cost guard must never round toward.
    """
    key = month_key or current_month_key()
    response = service_client.client.rpc(
        "clip_record_spend",
        {
            "p_month_key": key,
            "p_usd_micros": max(0, int(usd_micros)),
            "p_clips": max(0, int(clips)),
            "p_bytes": max(0, int(bytes_served)),
            "p_cap_usd_micros": monthly_cap_usd_micros(service_client),
        },
    ).execute()

    data = getattr(response, "data", None)
    if isinstance(data, int):
        return data
    if isinstance(data, list) and data and isinstance(data[0], int):
        return data[0]
    if isinstance(data, dict):
        total = data.get("total_usd_micros")
        if isinstance(total, int):
            return total
    return current_month_total_micros(service_client, month_key=key)


def reset_kill_switch(
    service_client: ServiceRoleClient, *, month_key: str | None = None
) -> bool:
    """Operator reversal. Recorded, not destructive — see :func:`is_killed`."""
    response = service_client.client.rpc(
        "reset_clip_kill_switch", {"p_month_key": month_key or current_month_key()}
    ).execute()
    return bool(getattr(response, "data", None))


def raise_if_killed(service_client: ServiceRoleClient) -> None:
    """Refuse an upload while the month's guard is tripped.

    Called at the ``POST /clips`` seam **only**. Nothing on the read path calls
    this: the feed, the share page and the shoppable overlay must keep working
    when the switch is on.
    """
    if is_killed(service_client):
        raise AppError(
            code="clip_cost_kill_switch",
            message="Clip uploads are paused for this month",
            http_status=503,
            details={"i18n_key": "clips.cost.paused", "message_key": "clips.cost.paused"},
        )


def headroom_micros(service_client: ServiceRoleClient) -> int:
    """How much of the month's cap is left. Never negative."""
    return max(
        0,
        monthly_cap_usd_micros(service_client) - current_month_total_micros(service_client),
    )
