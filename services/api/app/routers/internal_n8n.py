"""Internal n8n operational workflow data endpoints.

Logic stays in the API; n8n schedules and calls these endpoints. Sends are
enqueued to ``notification_outbox`` via the shared ``enqueue_outbox_row`` path
(M14-P01) and delivered by the notification-dispatch cron.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.notifications.dispatcher import has_any_channel_enabled
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/internal/n8n", tags=["internal-n8n"])

_INTERNAL_TOKEN_ENV = "INTERNAL_N8N_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-n8n"
_FOUNDER_PHONE_ENV = "FOUNDER_WHATSAPP_E164"
_DEFAULT_FOUNDER_PHONE = "+260970000000"
_LOW_STOCK_THRESHOLD_KEY = "low_stock_threshold"
_DEFAULT_LOW_STOCK_THRESHOLD = 5
_ABANDONED_CART_FLAG = "abandoned_cart"
_BATCH_LIMIT = 100
_MARKETING_EVENT_TYPES = frozenset(
    {"review_request", "kyc_nudge", "abandoned_cart"},
)

KYC_STALLED_HOURS = 48
REVIEW_REQUEST_HOURS = 24
PAYOUT_FAILURE_LOOKBACK_HOURS = 24


def _expected_internal_token() -> str:
    try:
        return resolve_internal_token(
            _INTERNAL_TOKEN_ENV,
            dev_default=_DEFAULT_INTERNAL_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_internal_n8n_token(request: Request) -> None:
    """Guard n8n-facing endpoints — not publicly callable without the shared token."""
    expected = _expected_internal_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal n8n token",
            http_status=401,
        )


def _table(client: Any, name: str) -> Any:
    return client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = response.data
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _iso_now() -> datetime:
    return datetime.now(UTC)


def _founder_phone_e164() -> str:
    return os.environ.get(_FOUNDER_PHONE_ENV, _DEFAULT_FOUNDER_PHONE).strip()


def _read_platform_config_int(client: Any, key: str, default: int) -> int:
    response = (
        _table(client, "platform_config").select("value").eq("key", key).maybe_single().execute()
    )
    data = response.data
    if not isinstance(data, dict):
        return default
    value = data.get("value")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _is_feature_flag_enabled(client: Any, flag: str) -> bool:
    response = (
        _table(client, "feature_flags").select("enabled").eq("flag", flag).maybe_single().execute()
    )
    data = response.data
    if isinstance(data, dict):
        return bool(data.get("enabled"))
    return False


def _load_profiles(
    client: Any,
    user_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not user_ids:
        return {}
    response = (
        _table(client, "profiles")
        .select("id, phone, locale, display_name, notif_prefs")
        .in_("id", sorted(user_ids))
        .execute()
    )
    return {str(row["id"]): row for row in _rows(response) if row.get("id")}


def _existing_dedupe_keys(
    client: Any,
    *,
    event_type: str,
) -> set[str]:
    prefix = f"{event_type}:"
    response = (
        _table(client, "notification_outbox")
        .select("dedupe_key")
        .like("dedupe_key", f"{prefix}%")
        .limit(5000)
        .execute()
    )
    return {
        str(row["dedupe_key"]) for row in _rows(response) if isinstance(row.get("dedupe_key"), str)
    }


def _envelope(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "count": len(items)}


def _tick_envelope(
    items: list[dict[str, Any]],
    *,
    enqueued: int,
    skipped: int,
) -> dict[str, Any]:
    return {
        "items": items,
        "count": len(items),
        "enqueued": enqueued,
        "skipped": skipped,
    }


def fetch_kyc_stalled(client: Any) -> list[dict[str, Any]]:
    """KYC records pending longer than 48h (stalled vendor applications)."""
    cutoff = (_iso_now() - timedelta(hours=KYC_STALLED_HOURS)).isoformat()
    response = (
        _table(client, "kyc_records")
        .select("id, vendor_id, tier, status, created_at, updated_at")
        .eq("status", "pending")
        .lt("updated_at", cutoff)
        .order("updated_at")
        .limit(_BATCH_LIMIT)
        .execute()
    )
    kyc_rows = _rows(response)
    if not kyc_rows:
        return []

    vendor_ids = {str(row["vendor_id"]) for row in kyc_rows if row.get("vendor_id")}
    vendor_response = (
        _table(client, "vendors")
        .select("id, owner_user_id, display_name, status")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    vendors_by_id = {str(row["id"]): row for row in _rows(vendor_response)}

    owner_ids = {
        str(vendor["owner_user_id"])
        for vendor in vendors_by_id.values()
        if vendor.get("owner_user_id")
    }
    profiles = _load_profiles(client, owner_ids)

    items: list[dict[str, Any]] = []
    for kyc in kyc_rows:
        vendor = vendors_by_id.get(str(kyc.get("vendor_id", "")))
        if vendor is None:
            continue
        owner_id = str(vendor.get("owner_user_id", ""))
        profile = profiles.get(owner_id, {})
        phone = profile.get("phone")
        if not isinstance(phone, str) or not phone.strip():
            continue
        items.append(
            {
                "kyc_record_id": str(kyc["id"]),
                "vendor_id": str(kyc["vendor_id"]),
                "vendor_name": str(vendor.get("display_name", "")),
                "tier": int(kyc.get("tier", 1)),
                "recipient_id": owner_id,
                "phone_e164": phone.strip(),
                "locale": str(profile.get("locale", "en")),
                "stalled_since": str(kyc.get("updated_at", "")),
            }
        )
    return items


def fetch_payout_failures(client: Any) -> list[dict[str, Any]]:
    """Recent failed payouts for founder alert."""
    cutoff = (_iso_now() - timedelta(hours=PAYOUT_FAILURE_LOOKBACK_HOURS)).isoformat()
    response = (
        _table(client, "payouts")
        .select("id, vendor_id, amount_ngwee, lenco_reference, status, updated_at")
        .eq("status", "failed")
        .gte("updated_at", cutoff)
        .order("updated_at", desc=True)
        .limit(_BATCH_LIMIT)
        .execute()
    )
    payout_rows = _rows(response)
    if not payout_rows:
        return []

    vendor_ids = {str(row["vendor_id"]) for row in payout_rows if row.get("vendor_id")}
    vendor_response = (
        _table(client, "vendors")
        .select("id, display_name, slug")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    vendors_by_id = {str(row["id"]): row for row in _rows(vendor_response)}
    founder_phone = _founder_phone_e164()

    items: list[dict[str, Any]] = []
    for payout in payout_rows:
        vendor = vendors_by_id.get(str(payout.get("vendor_id", "")))
        items.append(
            {
                "payout_id": str(payout["id"]),
                "vendor_id": str(payout["vendor_id"]),
                "vendor_name": str(vendor.get("display_name", "")) if vendor else "",
                "vendor_slug": str(vendor.get("slug", "")) if vendor else "",
                "amount_ngwee": int(payout.get("amount_ngwee", 0)),
                "lenco_reference": str(payout.get("lenco_reference", "")),
                "failed_at": str(payout.get("updated_at", "")),
                "recipient_id": "founder",
                "phone_e164": founder_phone,
                "locale": "en",
            }
        )
    return items


def fetch_low_stock(client: Any) -> list[dict[str, Any]]:
    """Active tracked listings at or below the low-stock threshold."""
    threshold = _read_platform_config_int(
        client,
        _LOW_STOCK_THRESHOLD_KEY,
        _DEFAULT_LOW_STOCK_THRESHOLD,
    )
    response = (
        _table(client, "vendor_listings")
        .select("id, vendor_id, title_override, stock_mode, stock_qty, status")
        .eq("status", "active")
        .eq("stock_mode", "tracked")
        .lte("stock_qty", threshold)
        .order("stock_qty")
        .limit(_BATCH_LIMIT)
        .execute()
    )
    listing_rows = _rows(response)
    if not listing_rows:
        return []

    vendor_ids = {str(row["vendor_id"]) for row in listing_rows if row.get("vendor_id")}
    vendor_response = (
        _table(client, "vendors")
        .select("id, owner_user_id, display_name")
        .in_("id", sorted(vendor_ids))
        .execute()
    )
    vendors_by_id = {str(row["id"]): row for row in _rows(vendor_response)}
    owner_ids = {
        str(vendor["owner_user_id"])
        for vendor in vendors_by_id.values()
        if vendor.get("owner_user_id")
    }
    profiles = _load_profiles(client, owner_ids)

    items: list[dict[str, Any]] = []
    for listing in listing_rows:
        vendor = vendors_by_id.get(str(listing.get("vendor_id", "")))
        if vendor is None:
            continue
        owner_id = str(vendor.get("owner_user_id", ""))
        profile = profiles.get(owner_id, {})
        phone = profile.get("phone")
        if not isinstance(phone, str) or not phone.strip():
            continue
        stock_qty = listing.get("stock_qty")
        items.append(
            {
                "listing_id": str(listing["id"]),
                "vendor_id": str(listing["vendor_id"]),
                "vendor_name": str(vendor.get("display_name", "")),
                "title": str(listing.get("title_override") or "Listing"),
                "stock_qty": int(stock_qty) if stock_qty is not None else 0,
                "threshold": threshold,
                "recipient_id": owner_id,
                "phone_e164": phone.strip(),
                "locale": str(profile.get("locale", "en")),
            }
        )
    return items


def fetch_review_requests(client: Any) -> list[dict[str, Any]]:
    """Completed orders 24h+ ago without a prior review-request notification."""
    completed_cutoff = (_iso_now() - timedelta(hours=REVIEW_REQUEST_HOURS)).isoformat()
    orders_response = (
        _table(client, "orders")
        .select("id, customer_id, vendor_id, status, updated_at")
        .eq("status", "completed")
        .limit(_BATCH_LIMIT)
        .execute()
    )
    order_rows = _rows(orders_response)
    if not order_rows:
        return []

    order_ids = [str(row["id"]) for row in order_rows]
    events_response = (
        _table(client, "order_events")
        .select("order_id, to_status, created_at")
        .in_("order_id", order_ids)
        .eq("to_status", "completed")
        .execute()
    )
    completed_at_by_order: dict[str, str] = {}
    for event in _rows(events_response):
        order_id = str(event.get("order_id", ""))
        created_at = str(event.get("created_at", ""))
        if order_id and created_at:
            existing = completed_at_by_order.get(order_id)
            if existing is None or created_at > existing:
                completed_at_by_order[order_id] = created_at

    existing_keys = _existing_dedupe_keys(client, event_type="review_request")

    vendor_ids = {str(row["vendor_id"]) for row in order_rows if row.get("vendor_id")}
    vendor_response = (
        _table(client, "vendors").select("id, display_name").in_("id", sorted(vendor_ids)).execute()
    )
    vendors_by_id = {str(row["id"]): row for row in _rows(vendor_response)}

    customer_ids = {str(row["customer_id"]) for row in order_rows if row.get("customer_id")}
    profiles = _load_profiles(client, customer_ids)

    items: list[dict[str, Any]] = []
    for order in order_rows:
        order_id = str(order["id"])
        completed_at = completed_at_by_order.get(order_id) or str(order.get("updated_at", ""))
        if completed_at >= completed_cutoff:
            continue
        dedupe_key = f"review_request:{order_id}:whatsapp"
        if dedupe_key in existing_keys:
            continue
        customer_id = str(order.get("customer_id", ""))
        profile = profiles.get(customer_id, {})
        phone = profile.get("phone")
        if not isinstance(phone, str) or not phone.strip():
            continue
        vendor = vendors_by_id.get(str(order.get("vendor_id", "")))
        items.append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "vendor_name": str(vendor.get("display_name", "")) if vendor else "",
                "completed_at": completed_at,
                "recipient_id": customer_id,
                "phone_e164": phone.strip(),
                "locale": str(profile.get("locale", "en")),
            }
        )
    return items


def fetch_abandoned_carts(client: Any) -> list[dict[str, Any]]:
    """Abandoned-cart recovery candidates — empty while feature flag is OFF."""
    if not _is_feature_flag_enabled(client, _ABANDONED_CART_FLAG):
        return []

    cutoff = (_iso_now() - timedelta(hours=24)).isoformat()
    response = (
        _table(client, "carts")
        .select("id, user_id, status, updated_at")
        .eq("status", "abandoned")
        .lt("updated_at", cutoff)
        .limit(_BATCH_LIMIT)
        .execute()
    )
    cart_rows = _rows(response)
    if not cart_rows:
        return []

    user_ids = {str(row["user_id"]) for row in cart_rows if row.get("user_id")}
    profiles = _load_profiles(client, user_ids)

    items: list[dict[str, Any]] = []
    for cart in cart_rows:
        user_id = cart.get("user_id")
        if not user_id:
            continue
        customer_id = str(user_id)
        profile = profiles.get(customer_id, {})
        phone = profile.get("phone")
        if not isinstance(phone, str) or not phone.strip():
            continue
        items.append(
            {
                "cart_id": str(cart["id"]),
                "recipient_id": customer_id,
                "phone_e164": phone.strip(),
                "locale": str(profile.get("locale", "en")),
                "abandoned_at": str(cart.get("updated_at", "")),
            }
        )
    return items


def _enqueue_items(
    client: Any,
    *,
    event_type: str,
    template: str,
    items: list[dict[str, Any]],
    entity_key: str,
) -> tuple[int, int]:
    enqueued = 0
    skipped = 0
    marketing = event_type in _MARKETING_EVENT_TYPES
    profiles_by_id: dict[str, dict[str, Any]] = {}
    if marketing and items:
        recipient_ids = {
            str(item["recipient_id"]) for item in items if item.get("recipient_id")
        }
        profiles_by_id = _load_profiles(client, recipient_ids)

    for item in items:
        if marketing:
            recipient_id = str(item.get("recipient_id", ""))
            profile = profiles_by_id.get(recipient_id, {})
            notif_prefs = profile.get("notif_prefs")
            prefs = notif_prefs if isinstance(notif_prefs, dict) else {}
            if not has_any_channel_enabled(prefs):
                skipped += 1
                continue
        entity_id = str(item[entity_key])
        row = enqueue_outbox_row(
            client.client,
            event_type=event_type,
            entity_id=entity_id,
            channel="whatsapp",
            template=template,
            payload=item,
        )
        if row is None:
            skipped += 1
        else:
            enqueued += 1
    return enqueued, skipped


@router.get(
    "/kyc-stalled",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def kyc_stalled(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _envelope(fetch_kyc_stalled(supabase))


@router.post(
    "/kyc-stalled/tick",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def kyc_stalled_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    items = fetch_kyc_stalled(supabase)
    enqueued, skipped = _enqueue_items(
        supabase,
        event_type="kyc_nudge",
        template="kyc_nudge",
        items=items,
        entity_key="kyc_record_id",
    )
    return _tick_envelope(items, enqueued=enqueued, skipped=skipped)


@router.get(
    "/payout-failures",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def payout_failures(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _envelope(fetch_payout_failures(supabase))


@router.post(
    "/payout-failures/tick",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def payout_failures_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    items = fetch_payout_failures(supabase)
    enqueued, skipped = _enqueue_items(
        supabase,
        event_type="payout_failure_alert",
        template="payout_failure_alert",
        items=items,
        entity_key="payout_id",
    )
    return _tick_envelope(items, enqueued=enqueued, skipped=skipped)


@router.get(
    "/low-stock",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def low_stock(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _envelope(fetch_low_stock(supabase))


@router.post(
    "/low-stock/tick",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def low_stock_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    items = fetch_low_stock(supabase)
    enqueued, skipped = _enqueue_items(
        supabase,
        event_type="low_stock_alert",
        template="low_stock_alert",
        items=items,
        entity_key="listing_id",
    )
    return _tick_envelope(items, enqueued=enqueued, skipped=skipped)


@router.get(
    "/review-requests",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def review_requests(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _envelope(fetch_review_requests(supabase))


@router.post(
    "/review-requests/tick",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def review_requests_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    items = fetch_review_requests(supabase)
    enqueued, skipped = _enqueue_items(
        supabase,
        event_type="review_request",
        template="review_request",
        items=items,
        entity_key="order_id",
    )
    return _tick_envelope(items, enqueued=enqueued, skipped=skipped)


@router.get(
    "/abandoned-carts",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def abandoned_carts(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    return _envelope(fetch_abandoned_carts(supabase))


@router.post(
    "/abandoned-carts/tick",
    dependencies=[Depends(require_internal_n8n_token)],
)
async def abandoned_carts_tick(
    supabase: Annotated[Any, Depends(get_supabase_client)],
) -> dict[str, Any]:
    items = fetch_abandoned_carts(supabase)
    enqueued, skipped = _enqueue_items(
        supabase,
        event_type="abandoned_cart",
        template="abandoned_cart_recovery",
        items=items,
        entity_key="cart_id",
    )
    return _tick_envelope(items, enqueued=enqueued, skipped=skipped)
