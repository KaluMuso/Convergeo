"""Read-only feature-flag helpers for service-layer callers.

`routers/beta.py` owns the launch-gate semantics of ``public_launch`` (invite
gate). This sibling exposes the same flag to service-layer code that only holds
a raw Supabase client (search, catalog). Fail-safe: any read error is treated
as "not public" — beta behaviour (demo visible, invite gate on) is the safe
default and matches `beta.is_public_launch`.
"""

from __future__ import annotations

from typing import Any

PUBLIC_LAUNCH_FLAG = "public_launch"


def is_public_launch(client: Any) -> bool:
    """Return True only when the ``public_launch`` feature flag is ON."""
    try:
        response = (
            client.table("feature_flags")
            .select("enabled")
            .eq("flag", PUBLIC_LAUNCH_FLAG)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        if not rows:
            return False
        return bool(rows[0].get("enabled"))
    except Exception:
        return False
