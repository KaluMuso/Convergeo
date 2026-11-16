"""Thin wrappers over the SECURITY DEFINER points functions (migration 20261116160000).

Every transition lives in SQL so it is idempotent by ``points_ledger.idempotency_key``
and serialised per user; Python only triggers it and reads results.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.db import run_sql_script

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class PointsError(RuntimeError):
    """The points SQL call failed."""


@dataclass(frozen=True, slots=True)
class PointsLiability:
    points_outstanding: int
    ngwee_per_point: int
    liability_ngwee: int


def _uuid(value: str) -> str:
    if not _UUID_RE.match(value):
        msg = "invalid uuid"
        raise ValueError(msg)
    return f"'{value}'::uuid"


def _ts(value: datetime | None) -> str:
    if value is None:
        return "timezone('utc', now())"
    return f"'{value.isoformat()}'::timestamptz"


def _one(script: str) -> str:
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        raise PointsError(result.error or "no row")
    return result.rows[0]


def award_order_points(order_id: str, *, now: datetime | None = None) -> str:
    """Try to earn for one order; returns the SQL outcome string."""
    return _one(f"SELECT private.points_award_order({_uuid(order_id)}, {_ts(now)});")


def try_award_after_release(order_id: str) -> None:
    """Escrow-release hook: best-effort, never breaks the release (the sweep retries)."""
    try:
        outcome = award_order_points(order_id)
    except Exception:  # noqa: BLE001 — points must never fail a money path
        logger.warning("points award after release skipped", extra={"order_id": order_id})
        return
    logger.info("points award after release", extra={"order_id": order_id, "outcome": outcome})


def run_points_sweep(*, now: datetime | None = None) -> dict[str, Any]:
    raw = _one(f"SELECT private.points_sweep({_ts(now)})::text;")
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def read_liability() -> PointsLiability:
    raw = json.loads(_one("SELECT public.points_liability()::text;"))
    return PointsLiability(
        points_outstanding=int(raw.get("points_outstanding", 0)),
        ngwee_per_point=int(raw.get("ngwee_per_point", 0)),
        liability_ngwee=int(raw.get("liability_ngwee", 0)),
    )
