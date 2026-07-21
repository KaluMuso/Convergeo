from __future__ import annotations

from typing import Any, Literal

SearchKind = Literal["products", "services", "events", "supplies", "vendors"]

_KIND_TO_ENTITY: dict[SearchKind, str] = {
    "products": "product",
    "services": "service",
    "events": "event",
    "supplies": "listing",
    "vendors": "vendor",
}

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def map_kind_to_entity_kind(kind: SearchKind | None) -> str | None:
    if kind is None:
        return None
    return _KIND_TO_ENTITY[kind]


def build_filters(
    *,
    kind: SearchKind | None = None,
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}

    entity_kind = map_kind_to_entity_kind(kind)
    if entity_kind is not None:
        filters["entity_kind"] = entity_kind

    if category_path is not None:
        trimmed = category_path.strip()
        if trimmed:
            filters["category_path"] = trimmed

    if price_min_ngwee is not None:
        filters["price_min_ngwee"] = price_min_ngwee

    if price_max_ngwee is not None:
        filters["price_max_ngwee"] = price_max_ngwee

    return filters


_FACET_KIND_ENTITY_GROUPS: dict[SearchKind, list[str]] = {
    "products": ["product", "listing"],
    "services": ["service"],
    "events": ["event"],
    "vendors": ["vendor"],
    "supplies": ["listing"],
}


def build_facet_rpc_filters(
    *,
    kind: SearchKind | None = None,
    category_path: str | None = None,
    price_min_ngwee: int | None = None,
    price_max_ngwee: int | None = None,
    include_wholesale: bool = False,
) -> dict[str, Any]:
    """Filters for ``search_query_facets`` RPC (entity scope + consumer exclusions)."""
    filters: dict[str, Any] = {
        "exclude_wholesale": not include_wholesale,
        "exclude_demo": True,
    }

    if kind is None or kind == "products":
        filters["entity_kinds"] = ["product", "listing"]
    elif kind in _FACET_KIND_ENTITY_GROUPS:
        filters["entity_kinds"] = _FACET_KIND_ENTITY_GROUPS[kind]

    if category_path is not None:
        trimmed = category_path.strip()
        if trimmed:
            filters["category_path"] = trimmed

    if price_min_ngwee is not None:
        filters["price_min_ngwee"] = price_min_ngwee

    if price_max_ngwee is not None:
        filters["price_max_ngwee"] = price_max_ngwee

    return filters


def normalize_page(page: int) -> int:
    return max(page, 1)


def normalize_page_size(page_size: int) -> int:
    if page_size < 1:
        return DEFAULT_PAGE_SIZE
    return min(page_size, MAX_PAGE_SIZE)


def paginate[T](items: list[T], *, page: int, page_size: int) -> tuple[list[T], int]:
    normalized_page = normalize_page(page)
    normalized_size = normalize_page_size(page_size)
    total = len(items)
    start = (normalized_page - 1) * normalized_size
    end = start + normalized_size
    return items[start:end], total
