"""Single answer to "may a customer see this entity right now?" for server-side
surfaces that read with the service role (RLS does not apply to them).

Mirrors the public RLS policies (0003 / 0058 / 20260813064106): a listing,
service or event is customer-visible only while its own status is public AND
its owning vendor is ``active``; a canonical product only while ``active``; a
vendor only while ``active``. Used by the ad resolver (a placement whose target
was hidden, blocked or removed never renders) and by admin target validation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

TargetKind = Literal["listing", "product", "service", "event", "vendor"]
TARGET_KINDS: tuple[TargetKind, ...] = ("listing", "product", "service", "event", "vendor")

# kind -> (table, public status, owning-vendor column or None, slug column or None)
_SPEC: dict[str, tuple[str, str, str | None, str | None]] = {
    "listing": ("vendor_listings", "active", "vendor_id", None),
    "product": ("products", "active", None, "slug"),
    "service": ("services", "active", "vendor_id", "slug"),
    "event": ("events", "published", "organiser_vendor_id", "slug"),
    "vendor": ("vendors", "active", None, "slug"),
}
_HREF_PREFIX = {
    "listing": "/l/",
    "product": "/p/",
    "service": "/s/",
    "event": "/e/",
    "vendor": "/v/",
}
_LABEL_COLUMN = {
    "listing": "title_override",
    "product": "name",
    "service": "title",
    "event": "title",
    "vendor": "display_name",
}


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def active_vendor_ids(client: Any, vendor_ids: Iterable[str]) -> set[str]:
    ids = sorted({str(value) for value in vendor_ids if value})
    if not ids:
        return set()
    rows = _rows(client.table("vendors").select("id, status").in_("id", ids).execute())
    return {str(row["id"]) for row in rows if row.get("status") == "active"}


def _select_columns(kind: str) -> str:
    _table, _status, vendor_column, slug_column = _SPEC[kind]
    columns = ["id", "status", _LABEL_COLUMN[kind]]
    if vendor_column:
        columns.append(vendor_column)
    if slug_column and slug_column not in columns:
        columns.append(slug_column)
    return ", ".join(columns)


def load_targets(client: Any, kind: str, ids: Iterable[str]) -> list[dict[str, Any]]:
    """Rows for ``ids`` with a computed ``visible`` flag, ``label`` and ``href``."""
    table, public_status, vendor_column, slug_column = _SPEC[kind]
    wanted = sorted({str(value) for value in ids if value})
    if not wanted:
        return []
    rows = _rows(client.table(table).select(_select_columns(kind)).in_("id", wanted).execute())
    return _annotate(client, kind, rows)


def search_targets(client: Any, kind: str, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    table, _status, _vendor, _slug = _SPEC[kind]
    label = _LABEL_COLUMN[kind]
    request = client.table(table).select(_select_columns(kind))
    term = query.strip()
    if term:
        request = request.ilike(label, f"%{term}%")
    rows = _rows(request.limit(limit).execute())
    return _annotate(client, kind, rows)


def _annotate(client: Any, kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _table, public_status, vendor_column, slug_column = _SPEC[kind]
    vendors = (
        active_vendor_ids(client, (str(row.get(vendor_column)) for row in rows))
        if vendor_column
        else set()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        visible = row.get("status") == public_status
        if vendor_column:
            visible = visible and str(row.get(vendor_column)) in vendors
        key = str(row.get(slug_column) if slug_column else row["id"])
        out.append(
            {
                "kind": kind,
                "id": str(row["id"]),
                "label": str(row.get(_LABEL_COLUMN[kind]) or row["id"]),
                "status": str(row.get("status") or ""),
                "vendor_id": str(row[vendor_column])
                if vendor_column and row.get(vendor_column)
                else None,
                "visible": visible,
                "href": f"{_HREF_PREFIX[kind]}{key}",
            }
        )
    return out


def visible_target_keys(client: Any, refs: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    """Subset of ``(kind, id)`` refs that customers may currently see."""
    by_kind: dict[str, set[str]] = {}
    for kind, entity_id in refs:
        if kind in _SPEC and entity_id:
            by_kind.setdefault(kind, set()).add(str(entity_id))
    visible: set[tuple[str, str]] = set()
    for kind, ids in by_kind.items():
        for row in load_targets(client, kind, ids):
            if row["visible"]:
                visible.add((kind, row["id"]))
    return visible
