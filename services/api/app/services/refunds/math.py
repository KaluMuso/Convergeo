"""Lane-1/lane-2 refund amount math — integer ngwee only (no float)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RESTOCKING_FEE_BPS = 1000
MIN_RESTOCKING_FEE_BPS = 500
MAX_RESTOCKING_FEE_BPS = 1500


def normalize_restocking_fee_bps(raw: int | None) -> int:
    """Clamp restocking fee bps to 500–1500; default 1000 when absent."""
    if raw is None:
        return DEFAULT_RESTOCKING_FEE_BPS
    return max(MIN_RESTOCKING_FEE_BPS, min(MAX_RESTOCKING_FEE_BPS, raw))


def restocking_fee_ngwee(*, item_ngwee: int, restocking_fee_bps: int) -> int:
    """floor(item × bps / 10000) — integer-exact."""
    if item_ngwee <= 0 or restocking_fee_bps <= 0:
        return 0
    return (item_ngwee * restocking_fee_bps) // 10_000


@dataclass(frozen=True, slots=True)
class Lane1RefundAmount:
    item_ngwee: int
    delivery_fee_ngwee: int
    refund_ngwee: int


@dataclass(frozen=True, slots=True)
class Lane2RefundBreakdown:
    item_ngwee: int
    outbound_delivery_ngwee: int
    return_transport_ngwee: int
    restocking_fee_bps: int
    restocking_fee_ngwee: int
    vendor_retained_ngwee: int
    refund_ngwee: int
    escrow_release_ngwee: int


def compute_lane1_refund(*, item_ngwee: int, delivery_fee_ngwee: int) -> Lane1RefundAmount:
    """Lane 1 — full refund including delivery."""
    item = max(0, item_ngwee)
    delivery = max(0, delivery_fee_ngwee)
    return Lane1RefundAmount(
        item_ngwee=item,
        delivery_fee_ngwee=delivery,
        refund_ngwee=item + delivery,
    )


def compute_lane2_refund(
    *,
    item_ngwee: int,
    outbound_delivery_ngwee: int,
    return_transport_ngwee: int,
    restocking_fee_bps: int,
) -> Lane2RefundBreakdown:
    """Lane 2 — item − outbound delivery − return transport − restocking fee (≥ 0)."""
    item = max(0, item_ngwee)
    outbound = max(0, outbound_delivery_ngwee)
    return_transport = max(0, return_transport_ngwee)
    bps = normalize_restocking_fee_bps(restocking_fee_bps)
    restocking = restocking_fee_ngwee(item_ngwee=item, restocking_fee_bps=bps)
    raw_refund = item - outbound - return_transport - restocking
    refund = max(0, raw_refund)
    vendor_retained = outbound + return_transport
    escrow_release = refund + vendor_retained + restocking
    return Lane2RefundBreakdown(
        item_ngwee=item,
        outbound_delivery_ngwee=outbound,
        return_transport_ngwee=return_transport,
        restocking_fee_bps=bps,
        restocking_fee_ngwee=restocking,
        vendor_retained_ngwee=vendor_retained,
        refund_ngwee=refund,
        escrow_release_ngwee=escrow_release,
    )
