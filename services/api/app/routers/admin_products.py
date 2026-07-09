from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.admin_base import router as admin_router
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

DUPLICATE_SIMILARITY_THRESHOLD = 0.3
MAX_DUPLICATE_PAIRS = 100

PRODUCT_STATUSES = frozenset({"pending_moderation", "active", "merged"})
MERGEABLE_STATUSES = frozenset({"pending_moderation", "active"})

products_router = APIRouter(prefix="/products", tags=["admin-products"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ProductSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    brand: str | None = None
    category_id: UUID
    status: str
    aliases: list[str] = Field(default_factory=list)


class DuplicatePairOut(BaseModel):
    product_a: ProductSummary
    product_b: ProductSummary
    similarity: float


class MergeProductsRequest(BaseModel):
    survivor_id: UUID
    loser_id: UUID


class MergeProductsResponse(BaseModel):
    survivor_id: UUID
    loser_id: UUID
    listings_repointed: int
    merged_aliases: list[str]
    slug_redirect_from: str
    slug_redirect_to: str
    idempotent: bool


class ProductMergeError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "product_merge_invalid",
        http_status: int = 409,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, http_status=http_status, details=details)


def _table(client: ServiceRoleClient, name: str) -> Any:
    return client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _normalize_trgm_text(text: str) -> str:
    return " ".join(text.lower().split())


def _trigrams(text: str) -> set[str]:
    padded = f"  {_normalize_trgm_text(text)} "
    if len(padded) < 3:
        return set()
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def pg_trgm_similarity(left: str, right: str) -> float:
    """Mirror PostgreSQL pg_trgm `similarity(text, text)` for title matching."""
    if left == right:
        return 1.0
    left_trigrams = _trigrams(left)
    right_trigrams = _trigrams(right)
    if not left_trigrams or not right_trigrams:
        return 0.0
    shared = len(left_trigrams & right_trigrams)
    return shared / max(len(left_trigrams), len(right_trigrams))


def _serialize_product(row: dict[str, Any]) -> ProductSummary:
    aliases_raw = row.get("aliases")
    aliases = [str(alias) for alias in aliases_raw] if isinstance(aliases_raw, list) else []
    brand = row.get("brand")
    return ProductSummary(
        id=UUID(str(row["id"])),
        name=str(row["name"]),
        slug=str(row["slug"]),
        brand=str(brand) if isinstance(brand, str) else None,
        category_id=UUID(str(row["category_id"])),
        status=str(row["status"]),
        aliases=aliases,
    )


def _load_product(client: ServiceRoleClient, product_id: str) -> dict[str, Any]:
    response = (
        _table(client, "products")
        .select("id, name, slug, brand, category_id, status, aliases, merged_into_id")
        .eq("id", product_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Product not found", http_status=404)
    return row


def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return (left_id, right_id) if left_id <= right_id else (right_id, left_id)


def find_duplicate_pairs(
    client: ServiceRoleClient,
    *,
    threshold: float = DUPLICATE_SIMILARITY_THRESHOLD,
    limit: int = MAX_DUPLICATE_PAIRS,
) -> list[DuplicatePairOut]:
    response = (
        _table(client, "products")
        .select("id, name, slug, brand, category_id, status, aliases, merged_into_id")
        .neq("status", "merged")
        .execute()
    )
    candidates = _rows(response)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        category_id = str(row.get("category_id") or "")
        if not category_id:
            continue
        by_category.setdefault(category_id, []).append(row)

    pairs: list[DuplicatePairOut] = []
    seen: set[tuple[str, str]] = set()
    for category_rows in by_category.values():
        for index, left in enumerate(category_rows):
            left_id = str(left["id"])
            left_name = str(left.get("name") or "")
            for right in category_rows[index + 1 :]:
                right_id = str(right["id"])
                key = _pair_key(left_id, right_id)
                if key in seen:
                    continue
                similarity = pg_trgm_similarity(left_name, str(right.get("name") or ""))
                if similarity < threshold:
                    continue
                seen.add(key)
                pairs.append(
                    DuplicatePairOut(
                        product_a=_serialize_product(left),
                        product_b=_serialize_product(right),
                        similarity=round(similarity, 4),
                    )
                )

    pairs.sort(key=lambda pair: pair.similarity, reverse=True)
    return pairs[:limit]


def _union_aliases(
    survivor_aliases: list[str],
    loser_aliases: list[str],
    *,
    loser_slug: str,
    survivor_slug: str,
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*survivor_aliases, *loser_aliases, loser_slug]:
        normalized = value.strip()
        if not normalized or normalized == survivor_slug or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def _guard_product_merge_transition(
    *,
    loser: dict[str, Any],
    survivor_id: str,
) -> bool:
    """Return True when merge is an idempotent no-op (loser already merged into survivor)."""
    status = str(loser.get("status") or "")
    merged_into_id = loser.get("merged_into_id")
    if status == "merged":
        if merged_into_id and str(merged_into_id) == survivor_id:
            return True
        raise ProductMergeError(
            "Loser product is already merged into a different canonical product",
            code="product_already_merged",
            http_status=409,
            details={
                "loser_id": str(loser["id"]),
                "merged_into_id": str(merged_into_id) if merged_into_id else None,
            },
        )
    if status not in MERGEABLE_STATUSES:
        raise ProductMergeError(
            f"Cannot merge product with status {status}",
            code="product_invalid_status",
            http_status=409,
            details={"status": status},
        )
    return False


def transition_product_merge(
    *,
    actor_id: str,  # noqa: ARG001 — reserved for future actor-scoped audit enrichment
    survivor_id: str,
    loser_id: str,
    service_client: ServiceRoleClient,
) -> tuple[dict[str, Any], bool]:
    if survivor_id == loser_id:
        raise ProductMergeError(
            "Cannot merge a product into itself",
            code="product_self_merge",
            http_status=400,
        )

    survivor = _load_product(service_client, survivor_id)
    loser = _load_product(service_client, loser_id)

    if str(survivor["category_id"]) != str(loser["category_id"]):
        raise ProductMergeError(
            "Cannot merge products across categories",
            code="product_cross_category_merge",
            http_status=409,
            details={
                "survivor_category_id": str(survivor["category_id"]),
                "loser_category_id": str(loser["category_id"]),
            },
        )

    idempotent = _guard_product_merge_transition(loser=loser, survivor_id=survivor_id)
    before = {
        "survivor": {
            "id": survivor["id"],
            "slug": survivor["slug"],
            "aliases": survivor.get("aliases") or [],
            "status": survivor["status"],
        },
        "loser": {
            "id": loser["id"],
            "slug": loser["slug"],
            "aliases": loser.get("aliases") or [],
            "status": loser["status"],
            "merged_into_id": loser.get("merged_into_id"),
        },
    }

    if idempotent:
        after = dict(before)
        return {
            "survivor_id": survivor_id,
            "loser_id": loser_id,
            "listings_repointed": 0,
            "merged_aliases": [
                str(alias)
                for alias in (survivor.get("aliases") or [])
                if isinstance(alias, str)
            ],
            "slug_redirect_from": str(loser["slug"]),
            "slug_redirect_to": str(survivor["slug"]),
            "before": before,
            "after": after,
        }, True

    listings_response = (
        _table(service_client, "vendor_listings")
        .select("id")
        .eq("product_id", loser_id)
        .execute()
    )
    listing_rows = _rows(listings_response)
    listings_repointed = 0
    if listing_rows:
        update_response = (
            _table(service_client, "vendor_listings")
            .update({"product_id": survivor_id})
            .eq("product_id", loser_id)
            .execute()
        )
        listings_repointed = len(_rows(update_response))

    survivor_aliases = [
        str(alias) for alias in (survivor.get("aliases") or []) if isinstance(alias, str)
    ]
    loser_aliases = [
        str(alias) for alias in (loser.get("aliases") or []) if isinstance(alias, str)
    ]
    merged_aliases = _union_aliases(
        survivor_aliases,
        loser_aliases,
        loser_slug=str(loser["slug"]),
        survivor_slug=str(survivor["slug"]),
    )

    loser_transition = (
        _table(service_client, "products")
        .update(
            {
                "status": "merged",
                "merged_into_id": survivor_id,
            }
        )
        .eq("id", loser_id)
        .in_("status", list(MERGEABLE_STATUSES))
        .execute()
    )
    if not _rows(loser_transition):
        refreshed_loser = _load_product(service_client, loser_id)
        if _guard_product_merge_transition(loser=refreshed_loser, survivor_id=survivor_id):
            after = dict(before)
            return {
                "survivor_id": survivor_id,
                "loser_id": loser_id,
                "listings_repointed": 0,
                "merged_aliases": merged_aliases,
                "slug_redirect_from": str(loser["slug"]),
                "slug_redirect_to": str(survivor["slug"]),
                "before": before,
                "after": after,
            }, True
        raise ProductMergeError(
            "Failed to transition loser product to merged status",
            code="product_merge_transition_failed",
            http_status=409,
        )

    touch_timestamp = datetime.now(UTC).isoformat()
    survivor_update = (
        _table(service_client, "products")
        .update(
            {
                "aliases": merged_aliases,
                "updated_at": touch_timestamp,
            }
        )
        .eq("id", survivor_id)
        .execute()
    )
    if not _rows(survivor_update):
        raise AppError(
            code="product_merge_failed",
            message="Failed to update survivor product aliases",
            http_status=500,
        )

    merged_after: dict[str, Any] = {
        "survivor": {
            "id": survivor["id"],
            "slug": survivor["slug"],
            "aliases": merged_aliases,
            "status": survivor["status"],
            "updated_at": touch_timestamp,
        },
        "loser": {
            "id": loser["id"],
            "slug": loser["slug"],
            "aliases": loser_aliases,
            "status": "merged",
            "merged_into_id": survivor_id,
        },
        "listings_repointed": listings_repointed,
    }

    return {
        "survivor_id": survivor_id,
        "loser_id": loser_id,
        "listings_repointed": listings_repointed,
        "merged_aliases": merged_aliases,
        "slug_redirect_from": str(loser["slug"]),
        "slug_redirect_to": str(survivor["slug"]),
        "before": before,
        "after": merged_after,
    }, False


@products_router.get("/duplicates", response_model=list[DuplicatePairOut])
async def list_duplicate_products(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[DuplicatePairOut]:
    return find_duplicate_pairs(service_client)


@products_router.post("/merge", response_model=MergeProductsResponse)
async def merge_products(
    body: MergeProductsRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> MergeProductsResponse:
    survivor_id = str(body.survivor_id)
    loser_id = str(body.loser_id)
    result, idempotent = transition_product_merge(
        actor_id=current_user.id,
        survivor_id=survivor_id,
        loser_id=loser_id,
        service_client=service_client,
    )

    recorder.record(
        action="admin.products.merge",
        entity_type="product",
        entity_id=survivor_id,
        before=result["before"],
        after=result["after"],
    )

    return MergeProductsResponse(
        survivor_id=UUID(survivor_id),
        loser_id=UUID(loser_id),
        listings_repointed=int(result["listings_repointed"]),
        merged_aliases=list(result["merged_aliases"]),
        slug_redirect_from=str(result["slug_redirect_from"]),
        slug_redirect_to=str(result["slug_redirect_to"]),
        idempotent=idempotent,
    )


admin_router.include_router(products_router)
