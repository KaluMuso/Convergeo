"""Pre-release vs post-release routing for refund ledger postings."""

from __future__ import annotations

from typing import Any, Protocol

RELEASE_KIND = "release_to_vendor"


class ServiceRoleClient(Protocol):
    client: Any


def order_funds_released(service_client: ServiceRoleClient, order_id: str) -> bool:
    """True when escrow has been released to vendor for this order."""
    response = (
        service_client.client.table("ledger_transactions")
        .select("id")
        .eq("order_id", order_id)
        .eq("kind", RELEASE_KIND)
        .limit(1)
        .execute()
    )
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data) > 0
    return False
