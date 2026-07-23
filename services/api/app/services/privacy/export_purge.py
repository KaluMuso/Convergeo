"""DPA retention: purge account-data-export bundles from Storage past their TTL.

`privacy.py` uploads each account-data export to
``private-artifacts/data-exports/{user_id}/{export_id}.json`` behind a 15-minute
signed URL, but the object itself is never deleted. These bundles contain the user's
personal data, so they must not linger — this sweep deletes bundles older than
``DATA_EXPORT_TTL_HOURS`` (default 24h; the signed URL is only valid for 15 min).

Design: the TTL decision (`select_expired`) is a **pure, unit-tested** function and the
orchestration (`purge_export_bundles`) takes **injected** list/remove callables, so the
logic is fully covered by fakes. The real Supabase-Storage adapter (`run_export_purge`)
is the one part that cannot be unit-tested here — no other code in `services/api` lists or
removes Storage objects — so it is **gated on a live smoke test** (drive the tick once on
staging, confirm `deleted` matches an aged fixture). Driven daily via
``POST /internal/privacy/export-purge-tick`` (n8n).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

# Mirror the export-creation constants in app/routers/privacy.py.
PRIVATE_EXPORT_BUCKET = "private-artifacts"
EXPORT_PATH_PREFIX = "data-exports"

_TTL_ENV = "DATA_EXPORT_TTL_HOURS"
_DEFAULT_TTL_HOURS = 24


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class StoredObject:
    """A Storage object: full path under the bucket + its creation time (UTC)."""

    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExportPurgeResult:
    scanned: int
    deleted: int


def export_ttl_hours() -> int:
    """Retention window in hours (env-tunable, positive int, default 24)."""
    raw = os.environ.get(_TTL_ENV, "").strip()
    if not raw:
        return _DEFAULT_TTL_HOURS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TTL_HOURS
    return value if value > 0 else _DEFAULT_TTL_HOURS


def parse_storage_timestamp(value: Any) -> datetime | None:
    """Parse a Storage ISO-8601 created_at into an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def select_expired(
    objects: list[StoredObject],
    *,
    now: datetime,
    ttl_hours: int,
) -> list[str]:
    """Names of export objects older than the TTL — the pure, testable core.

    Hard scope guard: only names under ``EXPORT_PATH_PREFIX/`` are ever returned, so a
    caller can never delete outside the data-exports prefix even if handed foreign objects.
    """
    cutoff = now - timedelta(hours=ttl_hours)
    return [
        obj.name
        for obj in objects
        if obj.name.startswith(f"{EXPORT_PATH_PREFIX}/") and obj.created_at < cutoff
    ]


def purge_export_bundles(
    *,
    list_objects: Any,
    remove_objects: Any,
    now: datetime | None = None,
    ttl_hours: int | None = None,
) -> ExportPurgeResult:
    """Orchestrate a purge with injected ``list_objects()`` / ``remove_objects(paths)``.

    Idempotent: a second run once nothing is aged past the TTL removes nothing.
    """
    current = now or datetime.now(UTC)
    ttl = ttl_hours if ttl_hours is not None else export_ttl_hours()
    objects: list[StoredObject] = list(list_objects())
    expired = select_expired(objects, now=current, ttl_hours=ttl)
    if expired:
        remove_objects(expired)
    return ExportPurgeResult(scanned=len(objects), deleted=len(expired))


# --- Real Supabase-Storage adapter (⚠ LIVE-SMOKE-GATED) ----------------------------
# No other code in services/api lists/removes Storage objects, so the exact accessor
# shapes below are unvalidated against a live stack. Confirm on staging before relying
# on it: upload a data-export, backdate it past the TTL, run the tick, assert deleted==1.


def _list_export_objects(service: ServiceRoleClient) -> list[StoredObject]:
    bucket = service.client.storage.from_(PRIVATE_EXPORT_BUCKET)
    out: list[StoredObject] = []
    # Layout is data-exports/<user_id>/<export_id>.json — list one level down per user.
    for folder in bucket.list(EXPORT_PATH_PREFIX) or []:
        folder_name = folder.get("name") if isinstance(folder, dict) else None
        if not isinstance(folder_name, str) or not folder_name:
            continue
        for entry in bucket.list(f"{EXPORT_PATH_PREFIX}/{folder_name}") or []:
            if not isinstance(entry, dict):
                continue
            file_name = entry.get("name")
            created = parse_storage_timestamp(
                entry.get("created_at") or (entry.get("metadata") or {}).get("lastModified")
            )
            if isinstance(file_name, str) and file_name and created is not None:
                out.append(
                    StoredObject(
                        name=f"{EXPORT_PATH_PREFIX}/{folder_name}/{file_name}",
                        created_at=created,
                    )
                )
    return out


def run_export_purge(
    service: ServiceRoleClient,
    *,
    now: datetime | None = None,
    ttl_hours: int | None = None,
) -> ExportPurgeResult:
    """Entry point for the internal tick — wires the real Storage list/remove."""
    bucket = service.client.storage.from_(PRIVATE_EXPORT_BUCKET)
    return purge_export_bundles(
        list_objects=lambda: _list_export_objects(service),
        remove_objects=lambda paths: bucket.remove(paths),
        now=now,
        ttl_hours=ttl_hours,
    )
