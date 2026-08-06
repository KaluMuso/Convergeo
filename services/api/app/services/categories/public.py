"""Public category tree reads (non-prohibited rows only)."""

from __future__ import annotations

from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.schemas.base import StrictModel

CATEGORIES_CACHE_KEY = "public:categories:v1"
CATEGORIES_CACHE_TTL_SECONDS = 3600  # 1 hour


class PublicCategory(StrictModel):
    id: str
    name: str
    slug: str
    path: str
    position: int
    parent_id: str | None = None
    prohibited: bool = False


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_public_categories_from_db(client: Any) -> list[PublicCategory]:
    response = (
        client.table("categories")
        .select("id, name, slug, path, position, parent_id, prohibited")
        .eq("prohibited", False)
        .order("position")
        .execute()
    )
    categories: list[PublicCategory] = []
    for row in _rows(response):
        category_id = row.get("id")
        name = row.get("name")
        slug = row.get("slug")
        path = row.get("path")
        position = row.get("position")
        if not category_id or not isinstance(name, str) or not isinstance(slug, str):
            continue
        if not isinstance(path, str) or not isinstance(position, int):
            continue
        parent_id = row.get("parent_id")
        categories.append(
            PublicCategory(
                id=str(category_id),
                name=name,
                slug=slug,
                path=path,
                position=position,
                parent_id=str(parent_id) if parent_id else None,
                prohibited=bool(row.get("prohibited")),
            )
        )
    return categories


def list_public_categories(
    client: Any,
    *,
    use_cache: bool = True,
    store: Any | None = None,
) -> list[PublicCategory]:
    if use_cache:
        cached = get_cached_json(CATEGORIES_CACHE_KEY, store=store)
        if isinstance(cached, list):
            try:
                return [PublicCategory.model_validate(item) for item in cached]
            except Exception:
                pass

    categories = load_public_categories_from_db(client)
    if use_cache:
        set_cached_json(
            CATEGORIES_CACHE_KEY,
            [category.model_dump(mode="json") for category in categories],
            ttl_seconds=CATEGORIES_CACHE_TTL_SECONDS,
            store=store,
        )
    return categories


def invalidate_public_categories_cache() -> None:
    """Best-effort cache bust (used by admin mutations in future)."""
    from app.core.ttl_cache import set_cached_json

    set_cached_json(CATEGORIES_CACHE_KEY, [], ttl_seconds=1)
