"""Platform config readers for refund execution."""

from __future__ import annotations

from typing import Any, Protocol

from app.services.refunds.math import normalize_restocking_fee_bps


class ServiceRoleClient(Protocol):
    client: Any


def _single_value(response: Any) -> Any | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data.get("value")
    return None


def load_restocking_fee_bps(service_client: ServiceRoleClient) -> int:
    """Read ``platform_config.restocking_fee_bps``; default 1000 when absent."""
    response = (
        service_client.client.table("platform_config")
        .select("value")
        .eq("key", "restocking_fee_bps")
        .maybe_single()
        .execute()
    )
    raw = _single_value(response)
    if isinstance(raw, bool):
        return normalize_restocking_fee_bps(None)
    if isinstance(raw, int):
        return normalize_restocking_fee_bps(raw)
    if isinstance(raw, float):
        return normalize_restocking_fee_bps(int(raw))
    if isinstance(raw, str):
        try:
            return normalize_restocking_fee_bps(int(raw))
        except ValueError:
            return normalize_restocking_fee_bps(None)
    return normalize_restocking_fee_bps(None)
