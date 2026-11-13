"""Venue capacity tree: Σ ticket-type allocations ≤ instance capacity."""

from __future__ import annotations

from typing import Any

from app.errors import AppError


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def assert_allocation_capacity_tree(
    *,
    instance_capacities: dict[str, int],
    other_allocated: dict[str, int],
    proposed: dict[str, int],
) -> None:
    """Raise 422 when any instance's allocated tiers would exceed venue capacity.

    ``other_allocated`` is the sum of allocations for *other* ticket types.
    Instances omitted from ``proposed`` contribute 0 for this type (cap removed).
    """
    instance_ids = set(instance_capacities) | set(other_allocated) | set(proposed)
    for instance_id in instance_ids:
        capacity = instance_capacities.get(instance_id)
        if capacity is None:
            continue
        total = other_allocated.get(instance_id, 0) + proposed.get(instance_id, 0)
        if total > capacity:
            raise AppError(
                code="allocation_exceeds_capacity",
                message="Ticket type allocations exceed instance capacity",
                http_status=422,
                details={
                    "instance_id": instance_id,
                    "capacity": capacity,
                    "allocated": total,
                    "message_key": "vendor.tickets.allocation.errors.exceedsCapacity",
                },
            )


def load_instance_capacities(client: Any, *, event_id: str) -> dict[str, int]:
    rows = _rows(
        client.table("event_instances").select("id, capacity").eq("event_id", event_id).execute()
    )
    result: dict[str, int] = {}
    for row in rows:
        instance_id = str(row.get("id") or "")
        if instance_id:
            result[instance_id] = int(row.get("capacity") or 0)
    return result


def load_other_type_allocated(
    client: Any,
    *,
    event_id: str,
    ticket_type_id: str,
) -> dict[str, int]:
    """Sum allocations for every type on this event except ``ticket_type_id``."""
    type_rows = _rows(client.table("ticket_types").select("id").eq("event_id", event_id).execute())
    other_ids = [
        str(row["id"]) for row in type_rows if row.get("id") and str(row["id"]) != ticket_type_id
    ]
    if not other_ids:
        return {}
    alloc_rows = _rows(
        client.table("ticket_type_instances")
        .select("instance_id, allocation")
        .in_("ticket_type_id", other_ids)
        .execute()
    )
    totals: dict[str, int] = {}
    for row in alloc_rows:
        instance_id = str(row.get("instance_id") or "")
        if not instance_id:
            continue
        totals[instance_id] = totals.get(instance_id, 0) + int(row.get("allocation") or 0)
    return totals
