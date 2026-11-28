"""Unified admin-controlled catalog taxonomy (20261127130000).

One logical tree per *umbrella* (product | service | event | wholesale) over three physical
tables, so existing slugs, ids and FKs never change:

* product + wholesale -> ``categories`` (uuid id, ``parent_id``, ``position``)
* service             -> ``service_categories`` (slug pk, ``parent_slug``, ``sort``)
* event               -> ``event_categories`` (slug pk, ``parent_slug``, ``sort``)

Every node is normalised to :class:`TaxonomyNode`. Public readers use
:func:`load_public_nodes` / :func:`allowed_slugs`, which filter on ``status = published`` and
the per-app visibility flags. Blocking never touches listings: they keep their category
reference and stay readable.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from app.errors import AppError
from app.schemas.base import StrictModel
from app.settings import get_settings

Umbrella = Literal["product", "service", "event", "wholesale"]
Status = Literal["draft", "published", "blocked"]
Audience = Literal["customer", "vendor"]

UMBRELLAS: tuple[str, ...] = ("product", "service", "event", "wholesale")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# Code constants the taxonomy replaced; used only when the DB has no rows for the umbrella
# (pre-migration environment, outage) so existing flows keep working.
FALLBACK_SERVICE_SLUGS: tuple[str, ...] = (
    "beauty",
    "food-catering",
    "auto",
    "printing-creative",
    "home-services",
    "tech-services",
    "cleaning",
    "tailoring",
)

_TABLES = {
    "product": "categories",
    "wholesale": "categories",
    "service": "service_categories",
    "event": "event_categories",
}
_SLUG_TABLES = {"service", "event"}
_COMMON = (
    "status, image_public_id, image_alt, icon, show_in_customer, show_in_vendor, "
    "updated_at, updated_by"
)
_SELECT = {
    "product": f"id, parent_id, name, slug, path, position, commission_key, umbrella, {_COMMON}",
    "wholesale": f"id, parent_id, name, slug, path, position, commission_key, umbrella, {_COMMON}",
    "service": f"slug, parent_slug, name, path, sort, is_active, {_COMMON}",
    "event": f"slug, parent_slug, name, label_key, sort, {_COMMON}",
}


class TaxonomyNode(StrictModel):
    id: str
    slug: str
    parent_id: str | None = None
    name: str
    umbrella: Umbrella
    status: Status
    sort_order: int = 0
    image_public_id: str | None = None
    image_alt: str | None = None
    image_url: str | None = None
    icon: str | None = None
    show_in_customer: bool = True
    show_in_vendor: bool = True
    path: str | None = None
    commission_key: str | None = None
    label_key: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    listing_count: int | None = None
    child_count: int = 0


def rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def table_for(umbrella: str) -> str:
    table = _TABLES.get(umbrella)
    if table is None:
        raise AppError(code="validation_error", message="Unknown umbrella", http_status=422)
    return table


def cloudinary_image_url(public_id: str | None, *, width: int = 160) -> str | None:
    """Public Cloudinary delivery URL (f_auto/q_auto, square crop) for a tile image."""
    if not public_id or not public_id.strip():
        return None
    try:
        cloud_name = get_settings().cloudinary_cloud_name
    except ValueError:
        return None
    normalized = public_id.strip().lstrip("/")
    return (
        f"https://res.cloudinary.com/{cloud_name}/image/upload/"
        f"c_fill,w_{width},h_{width},f_auto,q_auto/{normalized}"
    )


def normalize_row(umbrella: str, row: dict[str, Any]) -> TaxonomyNode:
    slug_table = umbrella in _SLUG_TABLES
    if slug_table:
        node_id = str(row["slug"])
        parent = row.get("parent_slug")
        sort_value = row.get("sort")
    else:
        node_id = str(row["id"])
        parent = row.get("parent_id")
        sort_value = row.get("position")
    slug = str(row["slug"])
    name = row.get("name")
    label = name if isinstance(name, str) and name.strip() else slug
    public_id = row.get("image_public_id")
    return TaxonomyNode(
        id=node_id,
        slug=slug,
        parent_id=str(parent) if parent else None,
        name=label,
        umbrella=umbrella,  # type: ignore[arg-type]
        status=row.get("status") or "published",
        sort_order=int(sort_value) if isinstance(sort_value, int) else 0,
        image_public_id=public_id if isinstance(public_id, str) else None,
        image_alt=row.get("image_alt"),
        image_url=cloudinary_image_url(public_id if isinstance(public_id, str) else None),
        icon=row.get("icon"),
        show_in_customer=bool(row.get("show_in_customer", True)),
        show_in_vendor=bool(row.get("show_in_vendor", True)),
        path=row.get("path") if isinstance(row.get("path"), str) else None,
        commission_key=row.get("commission_key"),
        label_key=row.get("label_key"),
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
        updated_by=str(row["updated_by"]) if row.get("updated_by") else None,
    )


def _base_query(client: Any, umbrella: str) -> Any:
    query = client.table(table_for(umbrella)).select(_SELECT[umbrella])
    if umbrella in ("product", "wholesale"):
        query = query.eq("umbrella", umbrella)
    return query


# ---------------------------------------------------------------------------
# Public reads (status + visibility filtered)
# ---------------------------------------------------------------------------
def load_public_nodes(client: Any, umbrella: str, audience: Audience) -> list[TaxonomyNode]:
    flag = "show_in_customer" if audience == "customer" else "show_in_vendor"
    query = _base_query(client, umbrella).eq("status", "published").eq(flag, True)
    if umbrella == "service":
        query = query.eq("is_active", True)
    order = "position" if umbrella in ("product", "wholesale") else "sort"
    nodes = [normalize_row(umbrella, row) for row in rows(query.order(order).execute())]
    return _drop_orphans(nodes)


def _drop_orphans(nodes: list[TaxonomyNode]) -> list[TaxonomyNode]:
    """A child is only reachable when its whole ancestor chain is visible."""
    by_id = {node.id: node for node in nodes}

    def reachable(node: TaxonomyNode, seen: frozenset[str] = frozenset()) -> bool:
        if node.parent_id is None:
            return True
        parent = by_id.get(node.parent_id)
        if parent is None or node.id in seen:
            return False
        return reachable(parent, seen | {node.id})

    return [node for node in nodes if reachable(node)]


def allowed_slugs(
    client: Any, umbrella: str, audience: Audience, fallback: tuple[str, ...]
) -> frozenset[str]:
    """Slugs a picker/validator may accept; falls back to constants when the DB is empty."""
    try:
        nodes = load_public_nodes(client, umbrella, audience)
        # An empty set may simply mean "nothing published yet" in a migrated DB. Distinguish
        # that from a missing/unseeded table by checking that the table has any row at all.
        if nodes:
            return frozenset(node.slug for node in nodes)
        any_rows = rows(client.table(table_for(umbrella)).select("slug").limit(1).execute())
        if any_rows:
            return frozenset()
    except Exception:  # noqa: BLE001 - pre-migration schema / fake clients
        pass
    return frozenset(fallback)


def public_service_verticals(client: Any) -> tuple[list[str], dict[str, str]]:
    """Customer-visible top-level service verticals (slugs in order, slug -> name)."""
    try:
        nodes = [n for n in load_public_nodes(client, "service", "customer") if not n.parent_id]
    except Exception:  # noqa: BLE001 - fake clients / pre-migration schema
        return [], {}
    return [n.slug for n in nodes], {n.slug: n.name for n in nodes}


def expand_service_category(client: Any, slug: str) -> list[str]:
    """Slug plus the slugs of its published descendants (browse filter by vertical)."""
    family = [slug]
    try:
        frontier = [slug]
        for _ in range(4):
            children = rows(
                client.table("service_categories")
                .select("slug")
                .in_("parent_slug", frontier)
                .eq("status", "published")
                .execute()
            )
            frontier = [str(r["slug"]) for r in children if str(r["slug"]) not in family]
            if not frontier:
                break
            family.extend(frontier)
    except Exception:  # noqa: BLE001 - fake clients / pre-migration schema
        return [slug]
    return family


# ---------------------------------------------------------------------------
# Admin reads
# ---------------------------------------------------------------------------
def listing_count(client: Any, umbrella: str, node: TaxonomyNode) -> int:
    """Catalog entities referencing this node (products / services / events)."""
    if umbrella in ("product", "wholesale"):
        table, column, value = "products", "category_id", node.id
    elif umbrella == "service":
        table, column, value = "services", "category", node.slug
    else:
        table, column, value = "events", "category_slug", node.slug
    response = (
        client.table(table).select(column, count="exact").eq(column, value).limit(1).execute()
    )
    exact = getattr(response, "count", None)
    if isinstance(exact, int):
        return exact
    return len(rows(response))


def list_admin_nodes(client: Any, umbrella: str, *, q: str = "") -> list[TaxonomyNode]:
    order = "position" if umbrella in ("product", "wholesale") else "sort"
    nodes = [
        normalize_row(umbrella, row)
        for row in rows(_base_query(client, umbrella).order(order).execute())
    ]
    children: dict[str, int] = {}
    for node in nodes:
        if node.parent_id:
            children[node.parent_id] = children.get(node.parent_id, 0) + 1
    for node in nodes:
        node.child_count = children.get(node.id, 0)
    term = q.strip().lower()
    if term:
        keep = {n.id for n in nodes if term in n.name.lower() or term in n.slug}
        # keep ancestors so matches stay inside their tree
        by_id = {n.id: n for n in nodes}
        for node_id in list(keep):
            cursor = by_id[node_id].parent_id
            while cursor and cursor in by_id and cursor not in keep:
                keep.add(cursor)
                cursor = by_id[cursor].parent_id
        nodes = [n for n in nodes if n.id in keep]
    return nodes


def get_node(client: Any, umbrella: str, node_id: str) -> TaxonomyNode:
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    try:
        found = rows(_base_query(client, umbrella).eq(key, node_id).limit(1).execute())
    except Exception as exc:  # noqa: BLE001 - malformed uuid etc.
        raise _not_found() from exc
    if not found:
        raise _not_found()
    node = normalize_row(umbrella, found[0])
    return node


def _not_found() -> AppError:
    return AppError(code="not_found", message="Category not found", http_status=404)


def _conflict(code: str, message: str, **details: Any) -> AppError:
    return AppError(code=code, message=message, http_status=409, details=details or None)


# ---------------------------------------------------------------------------
# Admin writes
# ---------------------------------------------------------------------------
def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().replace("&", "and")).strip("-")
    return slug or "category"


def _siblings(client: Any, umbrella: str, parent_id: str | None) -> list[TaxonomyNode]:
    return [n for n in list_admin_nodes(client, umbrella) if n.parent_id == parent_id]


def _validate_parent(
    client: Any, umbrella: str, parent_id: str | None, *, moving_id: str | None = None
) -> TaxonomyNode | None:
    if parent_id is None:
        return None
    parent = get_node(client, umbrella, parent_id)
    if moving_id is not None:
        cursor: TaxonomyNode | None = parent
        hops = 0
        while cursor is not None and hops < 20:
            if cursor.id == moving_id:
                raise _conflict("category_cycle", "A category cannot move under itself")
            cursor = get_node(client, umbrella, cursor.parent_id) if cursor.parent_id else None
            hops += 1
    return parent


def _path_for(parent: TaxonomyNode | None, slug: str) -> str:
    base = parent.path if parent is not None and parent.path else (parent.slug if parent else "")
    return f"{base}/{slug}" if base else slug


def create_node(
    client: Any,
    umbrella: str,
    *,
    name: str,
    slug: str | None,
    parent_id: str | None,
    fields: dict[str, Any],
    actor: str,
    commission_key: str | None = None,
) -> TaxonomyNode:
    final_slug = slug or slugify(name)
    if not SLUG_RE.fullmatch(final_slug):
        raise AppError(code="validation_error", message="Invalid slug", http_status=422)
    parent = _validate_parent(client, umbrella, parent_id)
    # Slugs are unique per physical table (global across product + wholesale).
    taken = rows(
        client.table(table_for(umbrella)).select("slug").eq("slug", final_slug).limit(1).execute()
    )
    if taken:
        raise _conflict("slug_taken", "Slug already in use", slug=final_slug)
    siblings = _siblings(client, umbrella, parent.id if parent else None)
    next_sort = (max((s.sort_order for s in siblings), default=0)) + 10
    payload: dict[str, Any] = {
        "name": name.strip(),
        "slug": final_slug,
        "updated_by": actor,
        **fields,
    }
    if umbrella in _SLUG_TABLES:
        payload["parent_slug"] = parent.slug if parent else None
        payload["sort"] = next_sort
        if umbrella == "service":
            payload["path"] = _path_for(parent, final_slug)
        else:
            payload["label_key"] = "events.categories.custom"
    else:
        payload["parent_id"] = parent.id if parent else None
        payload["position"] = next_sort
        payload["umbrella"] = umbrella
        payload["path"] = _path_for(parent, final_slug)
        payload["commission_key"] = commission_key or (
            parent.commission_key if parent and parent.commission_key else "default"
        )
    inserted = rows(client.table(table_for(umbrella)).insert(payload).execute())
    if not inserted:
        raise AppError(code="internal_error", message="Create failed", http_status=500)
    return get_node(client, umbrella, normalize_row(umbrella, inserted[0]).id)


def update_node(
    client: Any, umbrella: str, node_id: str, changes: dict[str, Any], *, actor: str
) -> TaxonomyNode:
    get_node(client, umbrella, node_id)  # 404 when missing
    payload = dict(changes)
    payload["updated_by"] = actor
    table = table_for(umbrella)
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    client.table(table).update(payload).eq(key, node_id).execute()
    return get_node(client, umbrella, node_id)


def move_node(
    client: Any, umbrella: str, node_id: str, new_parent_id: str | None, *, actor: str
) -> TaxonomyNode:
    node = get_node(client, umbrella, node_id)
    parent = _validate_parent(client, umbrella, new_parent_id, moving_id=node.id)
    siblings = _siblings(client, umbrella, parent.id if parent else None)
    next_sort = (max((s.sort_order for s in siblings), default=0)) + 10
    table = table_for(umbrella)
    payload: dict[str, Any] = {"updated_by": actor}
    if umbrella in _SLUG_TABLES:
        payload["parent_slug"] = parent.slug if parent else None
        payload["sort"] = next_sort
    else:
        payload["parent_id"] = parent.id if parent else None
        payload["position"] = next_sort
    if umbrella != "event":
        payload["path"] = _path_for(parent, node.slug)
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    client.table(table).update(payload).eq(key, node_id).execute()
    if umbrella != "event":
        _rewrite_descendant_paths(client, umbrella, node.id, _path_for(parent, node.slug))
    return get_node(client, umbrella, node_id)


def _rewrite_descendant_paths(client: Any, umbrella: str, root_id: str, root_path: str) -> None:
    nodes = list_admin_nodes(client, umbrella)
    kids: dict[str, list[TaxonomyNode]] = {}
    for node in nodes:
        if node.parent_id:
            kids.setdefault(node.parent_id, []).append(node)
    table = table_for(umbrella)
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    stack = [(root_id, root_path)]
    while stack:
        current, path = stack.pop()
        for child in kids.get(current, []):
            child_path = f"{path}/{child.slug}"
            client.table(table).update({"path": child_path}).eq(key, child.id).execute()
            stack.append((child.id, child_path))


def reorder_nodes(
    client: Any, umbrella: str, parent_id: str | None, ordered_ids: list[str], *, actor: str
) -> list[TaxonomyNode]:
    siblings = _siblings(client, umbrella, parent_id)
    expected = {s.id for s in siblings}
    if set(ordered_ids) != expected or len(ordered_ids) != len(expected):
        raise AppError(
            code="validation_error",
            message="ordered_ids must list every sibling exactly once",
            http_status=422,
        )
    table = table_for(umbrella)
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    column = "sort" if umbrella in _SLUG_TABLES else "position"
    for index, node_id in enumerate(ordered_ids, start=1):
        client.table(table).update({column: index * 10, "updated_by": actor}).eq(
            key, node_id
        ).execute()
    return [get_node(client, umbrella, node_id) for node_id in ordered_ids]


def delete_node(client: Any, umbrella: str, node_id: str) -> TaxonomyNode:
    """Delete only an unused leaf; anything referenced must be blocked instead."""
    node = get_node(client, umbrella, node_id)
    if any(n.parent_id == node.id for n in list_admin_nodes(client, umbrella)):
        raise _conflict("category_has_children", "Move or delete sub-categories first")
    count = listing_count(client, umbrella, node)
    if count > 0:
        raise _conflict(
            "category_has_listings",
            "Category has listings; block it instead of deleting",
            listing_count=count,
        )
    key = "slug" if umbrella in _SLUG_TABLES else "id"
    try:
        client.table(table_for(umbrella)).delete().eq(key, node_id).execute()
    except Exception as exc:  # noqa: BLE001 - FK restrict from tables we do not count
        raise _conflict("category_in_use", "Category is still referenced elsewhere") from exc
    return node
