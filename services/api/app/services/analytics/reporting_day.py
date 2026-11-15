"""Analytics reporting day (founder decision OD-9, 12 Nov 2026).

Every 1B rollup and admin analytics read buckets data by the **Africa/Lusaka** calendar
day (CAT, UTC+2). Stored timestamps stay UTC; only the day boundary moves — an event at
23:30 UTC belongs to the next Lusaka day. The SQL side uses ``'Africa/Lusaka'``
(``analytics_rollup_day`` / ``analytics_commercial_daily``).

Zambia has observed no DST since 1903 and has none legislated, so a fixed UTC+2 offset is
exact and avoids depending on the container's tzdata (``python:*-slim`` may lack it). A
unit test pins it against ``zoneinfo`` where tzdata exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Final

REPORTING_TZ_NAME: Final = "Africa/Lusaka"
REPORTING_TZ: Final = timezone(timedelta(hours=2), "CAT")


def reporting_today(now: datetime | None = None) -> date:
    """Today's analytics reporting day (Lusaka calendar date)."""
    return (now or datetime.now(UTC)).astimezone(REPORTING_TZ).date()
