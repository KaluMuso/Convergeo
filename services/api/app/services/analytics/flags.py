"""``analytics_v2`` server-side switches (plan §F.1).

``analytics_v2_collect`` and ``analytics_v2_rollups`` live in ``public.feature_flags``.
They are read through a short per-worker TTL cache so a busy beacon endpoint does not
read the flag table on every request; a flip takes effect within ``TTL_SECONDS``.

Fail closed: a missing row, an unreadable table or any error resolves to OFF — the v1
behaviour. A failed read is cached for the same TTL, so a DB outage cannot turn every
beacon into a flag query.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Final

from anyio import to_thread
from app.services.orders.audit import run_sql_script, sql_literal

logger = logging.getLogger(__name__)

COLLECT_FLAG: Final = "analytics_v2_collect"
ROLLUPS_FLAG: Final = "analytics_v2_rollups"
TTL_SECONDS: Final = 15.0

_cache: dict[str, tuple[float, bool]] = {}
_lock = threading.Lock()


def _read_flag(flag: str) -> bool:
    result = run_sql_script(
        "SELECT coalesce(enabled, false)::text FROM public.feature_flags "
        f"WHERE flag = {sql_literal(flag)} LIMIT 1;"
    )
    if not result.ok:
        logger.warning("analytics flag read failed; treating %s as off", flag)
        return False
    return bool(result.rows) and result.rows[0] in {"t", "true"}


def _cached(flag: str, clock: Callable[[], float]) -> bool | None:
    with _lock:
        entry = _cache.get(flag)
    if entry is not None and entry[0] > clock():
        return entry[1]
    return None


def _store(flag: str, value: bool, clock: Callable[[], float]) -> bool:
    with _lock:
        _cache[flag] = (clock() + TTL_SECONDS, value)
    return value


def flag_enabled(flag: str, *, clock: Callable[[], float] = time.monotonic) -> bool:
    """Synchronous read (for sync code paths and background jobs)."""
    cached = _cached(flag, clock)
    if cached is not None:
        return cached
    try:
        value = _read_flag(flag)
    except Exception:  # noqa: BLE001 — fail closed
        logger.warning("analytics flag read raised; treating %s as off", flag)
        value = False
    return _store(flag, value, clock)


async def flag_enabled_async(flag: str, *, clock: Callable[[], float] = time.monotonic) -> bool:
    """Async read: a cache miss runs the DB read in a worker thread, never on the loop."""
    cached = _cached(flag, clock)
    if cached is not None:
        return cached
    return await to_thread.run_sync(lambda: flag_enabled(flag, clock=clock))


def collect_v2_enabled() -> bool:
    return flag_enabled(COLLECT_FLAG)


async def collect_v2_enabled_async() -> bool:
    return await flag_enabled_async(COLLECT_FLAG)


def rollups_v2_enabled() -> bool:
    return flag_enabled(ROLLUPS_FLAG)


def snapshot() -> dict[str, bool | None]:
    """Cached flag values (None = not read yet) — for the ingest-stats endpoint."""
    now = time.monotonic()
    out: dict[str, bool | None] = {}
    with _lock:
        for flag in (COLLECT_FLAG, ROLLUPS_FLAG):
            expires, value = _cache.get(flag, (0.0, False))
            out[flag] = value if expires > now else None
    return out


def clear_cache() -> None:
    """Test helper."""
    with _lock:
        _cache.clear()


def override_for_tests(flag: str, value: bool) -> None:
    """Test helper: pin a flag value without touching the database."""
    with _lock:
        _cache[flag] = (float("inf"), value)
