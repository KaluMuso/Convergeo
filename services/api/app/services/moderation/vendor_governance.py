"""Vendor cancel-rate governance signal (F11 — strategy-gap audit).

Background: D9's preferred-badge gate already computes a vendor ``cancel_rate``
(``badge.MAX_CANCEL_RATE`` = 5%) and *revokes* the badge above it, but nothing
surfaces a rising cancel-rate to admins *before* it costs the badge, and there is
no "critical" tier for egregious offenders. The Product-Strategy audit flagged
this as F11 ("cancel-rate warn-5% / auto-suspend-10% not enforced").

This module adds the **read-only governance signal** the v1 manual-moderation
stance (§G IN — "manual admin moderation") was missing: it classifies every
active vendor's cancel-rate into ``ok`` / ``warn`` (>= 5%) / ``critical`` (>= 10%)
so an admin can review offenders and act with the *existing* manual controls
(``/flags/{id}/warn-vendor`` and ``/flags/{id}/escalate-suspend``). It deliberately
does **not** auto-suspend or mutate any vendor state — automated enforcement is a
separate, decision-gated follow-up (the audit's Phase-2 pointer), and suspension
already exists as a guarded manual action.

Single source of truth: the **warn** threshold is imported from
``badge.MAX_CANCEL_RATE`` so this signal can never disagree with the D9 badge
gate. The cancel-rate itself is ``cancelled / total`` over all of a vendor's
orders — identical to ``compute_badge_metrics`` — but computed here in a single
aggregate pass so an all-vendor scan costs two queries instead of four-per-vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from app.services.kyc.badge import MAX_CANCEL_RATE

# Warn at the same cancel-rate D9 uses to revoke the preferred badge; escalate to
# "critical" at double that. Below MIN_ORDERS_FOR_SIGNAL a percentage is noise
# (one cancel out of three is not a 33%-cancel vendor), so low-volume vendors are
# left to per-order/dispute review rather than a rate threshold.
WARN_CANCEL_RATE: float = MAX_CANCEL_RATE
CRITICAL_CANCEL_RATE: float = 0.10
MIN_ORDERS_FOR_SIGNAL: int = 10

Severity = Literal["ok", "warn", "critical"]

_SEVERITY_RANK: dict[Severity, int] = {"ok": 0, "warn": 1, "critical": 2}


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class VendorGovernanceSignal:
    vendor_id: str
    display_name: str | None
    slug: str | None
    status: str
    total_orders: int
    cancelled_orders: int
    cancel_rate: float
    severity: Severity


def classify_cancel_rate(cancel_rate: float, total_orders: int) -> Severity:
    """Bucket a vendor's cancel-rate into ok / warn / critical.

    Vendors below :data:`MIN_ORDERS_FOR_SIGNAL` are always ``ok`` — the denominator
    is too small for the rate to mean anything.
    """
    if total_orders < MIN_ORDERS_FOR_SIGNAL:
        return "ok"
    if cancel_rate >= CRITICAL_CANCEL_RATE:
        return "critical"
    if cancel_rate >= WARN_CANCEL_RATE:
        return "warn"
    return "ok"


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _signal_for(
    vendor: dict[str, Any],
    *,
    total_orders: int,
    cancelled_orders: int,
) -> VendorGovernanceSignal:
    cancel_rate = cancelled_orders / total_orders if total_orders else 0.0
    return VendorGovernanceSignal(
        vendor_id=str(vendor["id"]),
        display_name=(
            str(vendor["display_name"]) if vendor.get("display_name") is not None else None
        ),
        slug=str(vendor["slug"]) if vendor.get("slug") is not None else None,
        status=str(vendor.get("status", "")),
        total_orders=total_orders,
        cancelled_orders=cancelled_orders,
        cancel_rate=cancel_rate,
        severity=classify_cancel_rate(cancel_rate, total_orders),
    )


def _order_tallies(service_client: ServiceRoleClient) -> dict[str, tuple[int, int]]:
    """Return ``{vendor_id: (total_orders, cancelled_orders)}`` in one query."""
    response = service_client.client.table("orders").select("vendor_id, status").execute()
    tallies: dict[str, list[int]] = {}
    for row in _rows(response):
        vendor_id = row.get("vendor_id")
        if vendor_id is None:
            continue
        key = str(vendor_id)
        tally = tallies.setdefault(key, [0, 0])
        tally[0] += 1
        if str(row.get("status", "")) == "cancelled":
            tally[1] += 1
    return {key: (total, cancelled) for key, (total, cancelled) in tallies.items()}


def scan_vendor_governance(
    service_client: ServiceRoleClient,
    *,
    min_severity: Severity = "warn",
) -> list[VendorGovernanceSignal]:
    """Classify every active vendor by cancel-rate, most-severe first.

    Only signals at or above ``min_severity`` are returned. Two queries total:
    one for active vendors, one aggregate pass over orders.
    """
    threshold_rank = _SEVERITY_RANK[min_severity]
    vendors_response = (
        service_client.client.table("vendors")
        .select("id, display_name, slug, status")
        .eq("status", "active")
        .execute()
    )
    tallies = _order_tallies(service_client)

    signals: list[VendorGovernanceSignal] = []
    for vendor in _rows(vendors_response):
        total, cancelled = tallies.get(str(vendor.get("id")), (0, 0))
        signal = _signal_for(vendor, total_orders=total, cancelled_orders=cancelled)
        if _SEVERITY_RANK[signal.severity] >= threshold_rank:
            signals.append(signal)

    signals.sort(
        key=lambda s: (_SEVERITY_RANK[s.severity], s.cancel_rate, s.total_orders),
        reverse=True,
    )
    return signals
