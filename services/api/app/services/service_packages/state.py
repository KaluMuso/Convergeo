"""Service packages: tiers, snapshots and the guarded status transition.

Status moves only through :func:`transition_status`, which checks the transition
against :data:`ALLOWED_TRANSITIONS`, performs a compare-and-set update (the row
must still be in the expected status) and writes one ``audit_log`` row. Routers
never issue a raw status update (convention #4).
"""

from __future__ import annotations

import logging
from typing import Any, Final, Literal, Protocol

from app.errors import AppError

logger = logging.getLogger(__name__)

TABLE: Final = "service_packages"

Tier = Literal["basic", "standard", "premium"]
TIERS: Final[tuple[Tier, ...]] = ("basic", "standard", "premium")
TIER_ORDER: Final[dict[str, int]] = {tier: index for index, tier in enumerate(TIERS)}

ACTIVE: Final = "active"
ARCHIVED: Final = "archived"
ALLOWED_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {(ACTIVE, ARCHIVED), (ARCHIVED, ACTIVE)}
)

#: Columns exposed to callers (never the raw row).
PACKAGE_COLUMNS: Final = (
    "id, service_id, vendor_id, tier, name, description, price_ngwee, "
    "delivery_days, revisions, includes, status, updated_at"
)


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def sort_by_tier(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda row: TIER_ORDER.get(str(row.get("tier")), 99))


def int_or_none(value: Any) -> int | None:
    """Money/ints from the DB: accept ints only (bool and float are refused)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def snapshot(package: dict[str, Any]) -> dict[str, Any]:
    """What the customer saw, frozen onto the RFQ thread. Money stays an int."""
    includes = package.get("includes")
    return {
        "package_id": str(package.get("id") or ""),
        "tier": str(package.get("tier") or ""),
        "name": str(package.get("name") or ""),
        "price_ngwee": int_or_none(package.get("price_ngwee")),
        "delivery_days": int_or_none(package.get("delivery_days")),
        "revisions": int_or_none(package.get("revisions")),
        "includes": [str(item) for item in includes] if isinstance(includes, list) else [],
    }


def list_active_for_services(
    service_client: ServiceRoleClient, service_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Active packages per service, tier-ordered. Empty dict on no ids."""
    if not service_ids:
        return {}
    found = rows(
        service_client.client.table(TABLE)
        .select(PACKAGE_COLUMNS)
        .in_("service_id", service_ids)
        .eq("status", ACTIVE)
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        grouped.setdefault(str(row.get("service_id")), []).append(row)
    return {key: sort_by_tier(value) for key, value in grouped.items()}


def list_active_for_services_safe(
    service_client: ServiceRoleClient, service_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Read-path variant: a package read failure degrades to "no packages".

    The service page must never 500 because the optional package section could
    not be read (e.g. API deployed a moment before its migration).
    """
    try:
        return list_active_for_services(service_client, service_ids)
    except Exception:
        logger.warning("service package read failed; rendering without packages")
        return {}


def load_package(
    service_client: ServiceRoleClient, *, service_id: str, tier: str
) -> dict[str, Any] | None:
    found = rows(
        service_client.client.table(TABLE)
        .select(PACKAGE_COLUMNS)
        .eq("service_id", service_id)
        .eq("tier", tier)
        .maybe_single()
        .execute()
    )
    return found[0] if found else None


def transition_status(
    service_client: ServiceRoleClient,
    *,
    package: dict[str, Any],
    to_status: str,
    actor_id: str,
    reason: str,
) -> dict[str, Any]:
    """Guarded, audited ``active ↔ archived`` move. Replays are no-ops."""
    from_status = str(package.get("status") or "")
    if from_status == to_status:
        return package
    if (from_status, to_status) not in ALLOWED_TRANSITIONS:
        raise AppError(
            code="invalid_transition",
            message=f"Package cannot move from {from_status} to {to_status}",
            http_status=409,
            details={"message_key": "vendor.services.packages.errors.invalidTransition"},
        )
    package_id = str(package["id"])
    updated = rows(
        service_client.client.table(TABLE)
        .update({"status": to_status})
        .eq("id", package_id)
        .eq("status", from_status)
        .execute()
    )
    if not updated:
        # Lost a race with another transition; the caller can re-read and retry.
        raise AppError(
            code="conflict",
            message="Package changed concurrently",
            http_status=409,
            details={"message_key": "vendor.services.packages.errors.conflict"},
        )
    audit = rows(
        service_client.client.table("audit_log")
        .insert(
            {
                "actor": actor_id,
                "action": "service_package.transition",
                "entity_type": "service_package",
                "entity_id": package_id,
                "before": {"status": from_status},
                "after": {"status": to_status, "reason": reason},
            }
        )
        .execute()
    )
    if not audit:
        raise AppError(
            code="audit_write_failed",
            message="Failed to persist service package audit_log row",
            http_status=500,
        )
    return updated[0]
