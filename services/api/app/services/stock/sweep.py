from __future__ import annotations

from dataclasses import dataclass

from app.services.stock.claim import run_sql_script
from app.services.stock.release import ReleaseResult, release_reservation


@dataclass(frozen=True, slots=True)
class SweepResult:
    scanned: int
    released: int
    restocked_qty: int


def _fetch_expired_reservations() -> list[tuple[str, str]]:
    result = run_sql_script(
        """
        SELECT listing_id::text, checkout_group_id::text
        FROM public.stock_reservations
        WHERE expires_at < timezone('utc', now());
        """
    )
    if not result.ok:
        raise RuntimeError(f"fetch expired reservations failed: {result.error}")

    expired: list[tuple[str, str]] = []
    for row in result.rows:
        parts = row.split("|")
        if len(parts) == 2:
            expired.append((parts[0], parts[1]))
    return expired


def sweep_expired_reservations() -> SweepResult:
    expired = _fetch_expired_reservations()
    released = 0
    restocked_qty = 0

    for listing_id, checkout_group_id in expired:
        result: ReleaseResult = release_reservation(
            listing_id=listing_id,
            checkout_group_id=checkout_group_id,
        )
        if result.released:
            released += 1
            restocked_qty += result.qty

    return SweepResult(
        scanned=len(expired),
        released=released,
        restocked_qty=restocked_qty,
    )
