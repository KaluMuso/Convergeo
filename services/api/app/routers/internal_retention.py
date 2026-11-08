"""n8n tick: evaluate price-drop / back-in-stock subscriptions and saved-search
alerts, enqueueing notifications through the existing ``notification_outbox``
(idempotent via its UNIQUE dedupe key). Never sends directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.listings.availability import is_listing_available
from app.services.notifications.dedupe import enqueue_outbox_row
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter(prefix="/internal/retention", tags=["internal-retention"])

_INTERNAL_TOKEN_ENV = "INTERNAL_RETENTION_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-retention"
BATCH_LIMIT = 500
FREQUENCY_INTERVAL = {
    "instant": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}
LISTING_COLUMNS = (
    "id, price_ngwee, status, stock_mode, stock_qty, min_steps, moq, product_class, "
    "fulfilment_mode, vendor_capacity_per_week, title_override"
)


async def require_internal_retention_token(request: Request) -> None:
    try:
        expected = resolve_internal_token(_INTERNAL_TOKEN_ENV, dev_default=_DEFAULT_INTERNAL_TOKEN)
    except InternalTokenMisconfigured as exc:
        raise AppError(code="configuration_error", message=str(exc), http_status=503) from exc
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized", message="Invalid or missing internal token", http_status=401
        )


class TickResult(BaseModel):
    price_drop_enqueued: int = 0
    back_in_stock_enqueued: int = 0
    saved_search_enqueued: int = 0


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _in_stock(row: dict[str, Any]) -> bool:
    return is_listing_available(
        str(row.get("stock_mode") or "tracked"),
        row.get("stock_qty"),
        min_steps=int(row.get("min_steps") or 1),
        moq=int(row.get("moq") or 1),
        product_class=str(row.get("product_class") or "A"),
        fulfilment_mode=str(row.get("fulfilment_mode") or "stocked"),
        vendor_capacity_per_week=row.get("vendor_capacity_per_week"),
    )


def run_listing_alerts(client: Any, *, now: datetime, result: TickResult) -> None:
    subs = _rows(
        client.table("listing_alert_subscriptions")
        .select("id, user_id, listing_id, kind, baseline_price_ngwee, target_price_ngwee")
        .eq("active", True)
        .limit(BATCH_LIMIT)
        .execute()
    )
    listing_ids = sorted({str(sub["listing_id"]) for sub in subs})
    if not listing_ids:
        return
    listings = {
        str(row["id"]): row
        for row in _rows(
            client.table("vendor_listings").select(LISTING_COLUMNS).in_("id", listing_ids).execute()
        )
        if row.get("status") == "active"
    }
    for sub in subs:
        listing = listings.get(str(sub["listing_id"]))
        if listing is None:
            continue
        price = int(listing["price_ngwee"])
        payload = {
            "recipient_id": str(sub["user_id"]),
            "listing_id": str(sub["listing_id"]),
            "price_ngwee": price,
        }
        if sub["kind"] == "price_drop":
            baseline = int(sub.get("baseline_price_ngwee") or price)
            target = sub.get("target_price_ngwee")
            dropped = price < baseline and (target is None or price <= int(target))
            if not dropped or not _in_stock(listing):
                continue
            enqueue_outbox_row(
                client,
                event_type="price_drop",
                entity_id=f"{sub['id']}:{price}",
                channel="whatsapp",
                template="price_drop_alert",
                payload={**payload, "previous_price_ngwee": baseline},
            )
            client.table("listing_alert_subscriptions").update(
                {"baseline_price_ngwee": price, "last_notified_at": now.isoformat()}
            ).eq("id", sub["id"]).execute()
            result.price_drop_enqueued += 1
        elif sub["kind"] == "back_in_stock" and _in_stock(listing):
            enqueue_outbox_row(
                client,
                event_type="back_in_stock",
                entity_id=f"{sub['id']}:{now.date().isoformat()}",
                channel="whatsapp",
                template="back_in_stock_alert",
                payload=payload,
            )
            # One-shot: the shopper re-subscribes if it sells out again.
            client.table("listing_alert_subscriptions").update(
                {"active": False, "last_notified_at": now.isoformat()}
            ).eq("id", sub["id"]).execute()
            result.back_in_stock_enqueued += 1


def run_saved_search_alerts(client: Any, *, now: datetime, result: TickResult) -> None:
    searches = _rows(
        client.table("saved_searches")
        .select("id, user_id, query, filters, alert_frequency, last_alerted_at, created_at")
        .eq("alert_enabled", True)
        .limit(BATCH_LIMIT)
        .execute()
    )
    for search in searches:
        interval = FREQUENCY_INTERVAL.get(str(search.get("alert_frequency")), timedelta(days=1))
        last_raw = search.get("last_alerted_at") or search.get("created_at")
        last = (
            datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
            if last_raw
            else now - interval
        )
        if now - last < interval:
            continue
        query = (
            client.table("search_documents")
            .select("entity_id")
            .eq("entity_kind", "listing")
            .eq("is_public", True)
            .gt("updated_at", last.isoformat())
        )
        text = str(search.get("query") or "").strip()
        if text:
            escaped = text.replace("%", r"\%").replace("_", r"\_")
            query = query.ilike("title", f"%{escaped}%")
        filters = search.get("filters") or {}
        if isinstance(filters, dict):
            if filters.get("category_path"):
                query = query.like("category_path", f"{filters['category_path']}%")
            if isinstance(filters.get("max_price"), int):
                query = query.lte("price_min_ngwee", filters["max_price"])
            if isinstance(filters.get("min_price"), int):
                query = query.gte("price_min_ngwee", filters["min_price"])
        matches = _rows(query.limit(50).execute())
        if matches:
            enqueue_outbox_row(
                client,
                event_type="saved_search",
                entity_id=f"{search['id']}:{now.date().isoformat()}",
                channel="whatsapp",
                template="saved_search_alert",
                payload={
                    "recipient_id": str(search["user_id"]),
                    "saved_search_id": str(search["id"]),
                    "match_count": len(matches),
                },
            )
            result.saved_search_enqueued += 1
        client.table("saved_searches").update({"last_alerted_at": now.isoformat()}).eq(
            "id", search["id"]
        ).execute()


@router.post(
    "/alerts-tick",
    response_model=TickResult,
    dependencies=[Depends(require_internal_retention_token)],
)
async def alerts_tick() -> TickResult:
    service = next(get_supabase_client())
    now = datetime.now(UTC)
    result = TickResult()
    run_listing_alerts(service.client, now=now, result=result)
    run_saved_search_alerts(service.client, now=now, result=result)
    return result
