"""RFQ provider matching and broadcast notifications (M11-P02)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.notifications.dedupe import enqueue_outbox_row

DEFAULT_BROADCAST_CAP = 8
CONFIG_KEY_BROADCAST_CAP = "rfq_broadcast_cap"
RFQ_MATCH_EVENT = "rfq_job_broadcast"
RFQ_NO_MATCH_FLAG_REASON = "rfq_no_matching_providers"
SYSTEM_REPORTER_ID = "00000000-0000-0000-0000-000000000001"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class MatchedProvider:
    vendor_id: str
    service_id: str
    owner_user_id: str
    display_name: str
    preferred_badge: bool
    average_rating: float | None
    service_area: str | None
    rank_score: float


@dataclass(frozen=True, slots=True)
class BroadcastResult:
    job_id: str
    matched_count: int
    notified_count: int
    capped: bool
    no_match: bool
    admin_flagged: bool
    matched_vendor_ids: tuple[str, ...]


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


def _read_broadcast_cap(client: Any) -> int:
    response = (
        client.table("platform_config")
        .select("value")
        .eq("key", CONFIG_KEY_BROADCAST_CAP)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if not row:
        return DEFAULT_BROADCAST_CAP
    value = row.get("value")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else DEFAULT_BROADCAST_CAP
    if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        if inner.isdigit():
            parsed = int(inner)
            return parsed if parsed > 0 else DEFAULT_BROADCAST_CAP
    return DEFAULT_BROADCAST_CAP


def _normalize_area(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _proximity_score(service_area: str | None, requested_area: str) -> float:
    normalized_service = _normalize_area(service_area)
    normalized_request = _normalize_area(requested_area)
    if not normalized_request:
        return 0.0
    if normalized_service == normalized_request:
        return 100.0
    if normalized_service and (
        normalized_request in normalized_service or normalized_service in normalized_request
    ):
        return 50.0
    return 0.0


def _vendor_average_rating(client: Any, vendor_id: str) -> float | None:
    orders_response = (
        client.table("orders")
        .select("id")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    order_ids = [str(row["id"]) for row in _rows(orders_response) if row.get("id")]
    if not order_ids:
        return None

    items_response = (
        client.table("order_items")
        .select("id, order_id")
        .in_("order_id", order_ids)
        .execute()
    )
    order_id_by_item = {
        str(item["id"]): str(item["order_id"])
        for item in _rows(items_response)
        if item.get("id") and item.get("order_id")
    }
    if not order_id_by_item:
        return None

    reviews_response = (
        client.table("reviews")
        .select("rating, order_item_id")
        .eq("status", "published")
        .execute()
    )
    ratings: list[int] = []
    for review in _rows(reviews_response):
        item_id = str(review.get("order_item_id", ""))
        order_id = order_id_by_item.get(item_id)
        if order_id in order_ids and isinstance(review.get("rating"), int):
            ratings.append(review["rating"])
    if not ratings:
        return None
    return sum(ratings) / len(ratings)


def _rank_provider(
  *,
  preferred_badge: bool,
  average_rating: float | None,
  proximity: float,
) -> float:
    badge_score = 1000.0 if preferred_badge else 0.0
    rating_score = (average_rating or 0.0) * 100.0
    return badge_score + rating_score + proximity


def match_providers(
    service_client: ServiceRoleClient,
    *,
    category: str,
    service_area: str,
    cap: int | None = None,
) -> list[MatchedProvider]:
    """Select active services/vendors by category and service-area, rank, and cap."""
    client = service_client.client
    effective_cap = cap if cap is not None and cap > 0 else _read_broadcast_cap(client)

    services_response = (
        client.table("services")
        .select("id, vendor_id, category, service_area, status")
        .eq("status", "active")
        .eq("category", category)
        .execute()
    )
    services = _rows(services_response)
    if not services:
        return []

    vendor_ids = sorted({str(row["vendor_id"]) for row in services if row.get("vendor_id")})
    if not vendor_ids:
        return []

    vendors_response = (
        client.table("vendors")
        .select("id, owner_user_id, display_name, preferred_badge, status")
        .in_("id", vendor_ids)
        .eq("status", "active")
        .execute()
    )
    vendors_by_id = {
        str(row["id"]): row for row in _rows(vendors_response) if row.get("id")
    }

    candidates: list[MatchedProvider] = []
    seen_vendors: set[str] = set()
    for service in services:
        vendor_id = str(service.get("vendor_id", ""))
        if not vendor_id or vendor_id in seen_vendors:
            continue
        vendor = vendors_by_id.get(vendor_id)
        if vendor is None:
            continue

        area = service.get("service_area")
        if isinstance(area, str):
            proximity = _proximity_score(area, service_area)
        else:
            proximity = 0.0
        if proximity <= 0.0 and _normalize_area(service_area):
            continue

        average_rating = _vendor_average_rating(client, vendor_id)
        preferred_badge = bool(vendor.get("preferred_badge"))
        rank_score = _rank_provider(
            preferred_badge=preferred_badge,
            average_rating=average_rating,
            proximity=proximity,
        )
        candidates.append(
            MatchedProvider(
                vendor_id=vendor_id,
                service_id=str(service["id"]),
                owner_user_id=str(vendor.get("owner_user_id", "")),
                display_name=str(vendor.get("display_name", "")),
                preferred_badge=preferred_badge,
                average_rating=average_rating,
                service_area=area if isinstance(area, str) else None,
                rank_score=rank_score,
            )
        )
        seen_vendors.add(vendor_id)

    candidates.sort(
        key=lambda item: (
            -item.rank_score,
            -(item.average_rating or 0.0),
            item.display_name.lower(),
        )
    )
    return candidates[:effective_cap]


def _flag_job_for_admin(
    client: Any,
    *,
    job_id: str,
    customer_id: str,
    category: str,
    service_area: str,
) -> bool:
    existing = (
        client.table("flags")
        .select("id")
        .eq("entity_type", "job")
        .eq("entity_id", job_id)
        .eq("reason", RFQ_NO_MATCH_FLAG_REASON)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    if _rows(existing):
        return False

    client.table("flags").insert(
        {
            "entity_type": "job",
            "entity_id": job_id,
            "reason": RFQ_NO_MATCH_FLAG_REASON,
            "reporter_user_id": customer_id,
            "status": "open",
        }
    ).execute()
    client.table("audit_log").insert(
        {
            "actor": SYSTEM_REPORTER_ID,
            "action": "rfq.no_match_admin_flag",
            "entity_type": "job",
            "entity_id": job_id,
            "before": None,
            "after": {
                "category": category,
                "service_area": service_area,
                "reason": RFQ_NO_MATCH_FLAG_REASON,
            },
        }
    ).execute()
    return True


def broadcast_job(
    service_client: ServiceRoleClient,
    *,
    job_id: str,
    customer_id: str,
    category: str,
    service_area: str,
    description: str,
) -> BroadcastResult:
    """Notify matched providers via outbox; flag admin when no matches."""
    client = service_client.client
    cap = _read_broadcast_cap(client)
    providers = match_providers(
        service_client,
        category=category,
        service_area=service_area,
        cap=cap,
    )

    if not providers:
        admin_flagged = _flag_job_for_admin(
            client,
            job_id=job_id,
            customer_id=customer_id,
            category=category,
            service_area=service_area,
        )
        return BroadcastResult(
            job_id=job_id,
            matched_count=0,
            notified_count=0,
            capped=False,
            no_match=True,
            admin_flagged=admin_flagged,
            matched_vendor_ids=(),
        )

    notified = 0
    for provider in providers:
        payload = {
            "job_id": job_id,
            "vendor_id": provider.vendor_id,
            "service_id": provider.service_id,
            "category": category,
            "service_area": service_area,
            "description_preview": description[:160],
            "recipient_user_id": provider.owner_user_id,
        }
        row = enqueue_outbox_row(
            client,
            event_type=RFQ_MATCH_EVENT,
            entity_id=f"{job_id}:{provider.vendor_id}",
            channel="whatsapp",
            template=None,
            payload=payload,
        )
        if row is not None:
            notified += 1

    all_matches = match_providers(
        service_client,
        category=category,
        service_area=service_area,
        cap=None,
    )
    return BroadcastResult(
        job_id=job_id,
        matched_count=len(providers),
        notified_count=notified,
        capped=len(all_matches) > cap,
        no_match=False,
        admin_flagged=False,
        matched_vendor_ids=tuple(provider.vendor_id for provider in providers),
    )
