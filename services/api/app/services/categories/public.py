"""Public category tree reads (non-prohibited rows only)."""

from __future__ import annotations

from typing import Any

from app.core.ttl_cache import get_cached_json, set_cached_json
from app.schemas.base import StrictModel
from app.services.categories.taxonomy import cloudinary_image_url

CATEGORIES_CACHE_KEY = "public:categories:v2"
# Short TTL: admin publish/block must reach the customer menu within minutes.
CATEGORIES_CACHE_TTL_SECONDS = 300


class PublicCategory(StrictModel):
    id: str
    name: str
    slug: str
    path: str
    position: int
    parent_id: str | None = None
    prohibited: bool = False
    umbrella: str = "product"
    image_url: str | None = None
    image_alt: str | None = None
    icon: str | None = None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_public_categories_from_db(client: Any) -> list[PublicCategory]:
    response = (
        client.table("categories")
        .select(
            "id, name, slug, path, position, parent_id, prohibited, umbrella, "
            "image_public_id, image_alt, icon"
        )
        .eq("prohibited", False)
        .eq("status", "published")
        .eq("show_in_customer", True)
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
                umbrella=str(row.get("umbrella") or "product"),
                image_url=cloudinary_image_url(
                    row.get("image_public_id")
                    if isinstance(row.get("image_public_id"), str)
                    else None
                ),
                image_alt=row.get("image_alt") if isinstance(row.get("image_alt"), str) else None,
                icon=row.get("icon") if isinstance(row.get("icon"), str) else None,
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
    """Bust public taxonomy caches after an admin mutation (readers reload on non-list)."""
    from app.services.categories import taxonomy_public

    set_cached_json(CATEGORIES_CACHE_KEY, {"stale": True}, ttl_seconds=1)
    taxonomy_public.invalidate()
