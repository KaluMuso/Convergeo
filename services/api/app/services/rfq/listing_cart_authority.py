"""Server-side authority for RFQ-pinned cart lines (accepted listing RFQ quotes).

Accepted-quote semantics (RECOMMENDED — not explicit in D1–D37):
  * ``quote_valid_until`` governs whether the customer may ACCEPT the quote.
  * Once validly accepted and pinned on a cart line, the quote price stays
    authoritative for that line through checkout and order snapshot.
  * Listing availability, inventory, and class-specific fulfilment rules still apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

THREAD_SELECT = (
    "id, customer_id, listing_id, status, quote_price_ngwee, quote_valid_until"
)


def is_rfq_pinned_line(item: dict[str, Any]) -> bool:
    rfq_thread_id = item.get("rfq_thread_id")
    return isinstance(rfq_thread_id, str) and rfq_thread_id.strip() != ""


def fetch_rfq_threads_for_items(
    service_client: Any,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Batch-load RFQ threads referenced by cart lines (service-role client)."""
    thread_ids: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not is_rfq_pinned_line(item):
            continue
        thread_id = str(item["rfq_thread_id"]).strip()
        if thread_id in seen:
            continue
        seen.add(thread_id)
        thread_ids.append(thread_id)
    if not thread_ids:
        return {}

    response = (
        service_client.table("rfq_threads")
        .select(THREAD_SELECT)
        .in_("id", thread_ids)
        .execute()
    )
    rows = response.data if isinstance(response.data, list) else []
    threads: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id") is not None:
            threads[str(row["id"])] = row
    return threads


@dataclass(frozen=True, slots=True)
class RfqPinnedAuthority:
    quote_price_ngwee: int


def validate_rfq_pinned_line_authority(
    *,
    rfq_thread_id: str,
    customer_id: str,
    listing_id: str,
    stored_unit_price_ngwee: int,
    thread: dict[str, Any] | None,
) -> tuple[RfqPinnedAuthority | None, str | None, dict[str, Any]]:
    """Validate an RFQ-pinned cart line against the authoritative thread row.

    Returns ``(authority, conflict_code, conflict_details)``. ``conflict_code`` is
  None when the line is authorized. Details are empty when not applicable.
    """
    if thread is None:
        return None, "rfq.not_found", {"rfq_thread_id": rfq_thread_id}

    if str(thread.get("customer_id")) != customer_id:
        return None, "rfq.not_found", {"rfq_thread_id": rfq_thread_id}

    thread_listing = thread.get("listing_id")
    if thread_listing is None or str(thread_listing) != listing_id:
        return None, "rfq.listing_mismatch", {
            "rfq_thread_id": rfq_thread_id,
            "listing_id": listing_id,
        }

    status = str(thread.get("status"))
    if status != "accepted":
        return None, "rfq.not_accepted", {
            "rfq_thread_id": rfq_thread_id,
            "status": status,
        }

    quote_raw = thread.get("quote_price_ngwee")
    if quote_raw is None or int(quote_raw) <= 0:
        return None, "rfq.no_quote_price", {"rfq_thread_id": rfq_thread_id}

    authoritative = int(quote_raw)
    if stored_unit_price_ngwee != authoritative:
        return None, "cart.price_changed", {
            "previous_unit_price_ngwee": stored_unit_price_ngwee,
            "current_unit_price_ngwee": authoritative,
        }

    return RfqPinnedAuthority(quote_price_ngwee=authoritative), None, {}
