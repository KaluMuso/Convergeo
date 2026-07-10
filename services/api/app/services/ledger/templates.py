"""Double-entry posting templates — the sole write path for ledger postings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.schemas.base import parse_ngwee

PLATFORM_ACCOUNT_KINDS = frozenset(
    {"platform_cash", "escrow", "commission_revenue", "fees"}
)
VENDOR_ACCOUNT_KINDS = frozenset({"vendor_payable", "cod_receivable"})


class LedgerTemplate(StrEnum):
    CHARGE_RECEIVED = "charge_received"
    ESCROW_HOLD = "escrow_hold"
    COMMISSION_CAPTURE = "commission_capture"
    RELEASE_TO_VENDOR = "release_to_vendor"
    PAYOUT_EXECUTED = "payout_executed"
    REFUND_LANE1 = "refund_lane1"
    REFUND_LANE2 = "refund_lane2"
    COD_COLLECTED = "cod_collected"
    CLAWBACK = "clawback"


@dataclass(frozen=True, slots=True)
class AccountRef:
    """Chart-of-accounts reference resolved to a ledger_accounts row at post time."""

    kind: str
    vendor_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind in VENDOR_ACCOUNT_KINDS and self.vendor_id is None:
            msg = f"vendor_id is required for account kind {self.kind!r}"
            raise ValueError(msg)
        if self.kind in PLATFORM_ACCOUNT_KINDS and self.vendor_id is not None:
            msg = f"vendor_id must be null for platform account kind {self.kind!r}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PostingLeg:
    account: AccountRef
    amount_ngwee: int


@dataclass(frozen=True, slots=True)
class TemplateResult:
    kind: str
    legs: tuple[PostingLeg, ...]
    checkout_group_id: str | None = None
    order_id: str | None = None
    payment_id: str | None = None
    payout_id: str | None = None
    refund_id: str | None = None


def commission_ngwee_from_bps(*, gross_ngwee: int, commission_bps: int) -> int:
    """Integer-exact bps → ngwee (no float)."""
    gross = parse_ngwee(gross_ngwee)
    if commission_bps < 0:
        msg = "commission_bps must be non-negative"
        raise ValueError(msg)
    return (gross * commission_bps) // 10_000


def _assert_balanced(legs: tuple[PostingLeg, ...]) -> None:
    total = sum(leg.amount_ngwee for leg in legs)
    if total != 0:
        msg = f"posting legs must sum to zero (got {total} ngwee)"
        raise ValueError(msg)
    if not legs:
        msg = "posting legs must not be empty"
        raise ValueError(msg)
    for leg in legs:
        if leg.amount_ngwee == 0:
            msg = "posting leg amount_ngwee must be non-zero"
            raise ValueError(msg)


def charge_received(*, gross_ngwee: int) -> TemplateResult:
    """Payment confirmed — Lenco collection credited to platform cash and held in escrow.

    Debit platform_cash (+gross).
    Credit escrow (−gross).
    """
    gross = parse_ngwee(gross_ngwee)
    legs = (
        PostingLeg(AccountRef("platform_cash"), gross),
        PostingLeg(AccountRef("escrow"), -gross),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.CHARGE_RECEIVED, legs=legs)


def escrow_hold(*, order_amount_ngwee: int) -> TemplateResult:
    """Order-level escrow reservation after checkout payment (per-order allocation).

    Debit platform_cash (+order_amount).
    Credit escrow (−order_amount).
    """
    amount = parse_ngwee(order_amount_ngwee)
    legs = (
        PostingLeg(AccountRef("platform_cash"), amount),
        PostingLeg(AccountRef("escrow"), -amount),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.ESCROW_HOLD, legs=legs)


def commission_capture(*, gross_ngwee: int, commission_bps: int) -> TemplateResult:
    """Capture platform commission from escrow at release time.

    Debit escrow (+commission).
    Credit commission_revenue (−commission).

    Commission is computed from gross via integer bps math.
    """
    gross = parse_ngwee(gross_ngwee)
    commission = commission_ngwee_from_bps(gross_ngwee=gross, commission_bps=commission_bps)
    if commission <= 0 or commission > gross:
        msg = "commission must be positive and not exceed gross"
        raise ValueError(msg)
    legs = (
        PostingLeg(AccountRef("escrow"), commission),
        PostingLeg(AccountRef("commission_revenue"), -commission),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.COMMISSION_CAPTURE, legs=legs)


def release_to_vendor(*, net_ngwee: int, vendor_id: str) -> TemplateResult:
    """Release net vendor share from escrow to vendor payable.

    Debit escrow (+net).
    Credit vendor_payable (vendor) (−net).
    """
    net = parse_ngwee(net_ngwee)
    legs = (
        PostingLeg(AccountRef("escrow"), net),
        PostingLeg(AccountRef("vendor_payable", vendor_id), -net),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.RELEASE_TO_VENDOR, legs=legs)


def payout_executed(*, amount_ngwee: int, vendor_id: str) -> TemplateResult:
    """Vendor payout sent via Lenco — clear payable and reduce platform cash.

    Debit vendor_payable (vendor) (+amount).
    Credit platform_cash (−amount).
    """
    amount = parse_ngwee(amount_ngwee)
    legs = (
        PostingLeg(AccountRef("vendor_payable", vendor_id), amount),
        PostingLeg(AccountRef("platform_cash"), -amount),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.PAYOUT_EXECUTED, legs=legs)


def refund_lane1(*, refund_ngwee: int) -> TemplateResult:
    """Lane 1 full refund (faulty/wrong) — return funds from escrow to platform cash.

    Debit escrow (+refund).
    Credit platform_cash (−refund).
    """
    refund = parse_ngwee(refund_ngwee)
    legs = (
        PostingLeg(AccountRef("escrow"), refund),
        PostingLeg(AccountRef("platform_cash"), -refund),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.REFUND_LANE1, legs=legs)


def refund_lane2(
    *,
    escrow_release_ngwee: int,
    refund_to_customer_ngwee: int,
    vendor_retained_ngwee: int,
    restocking_fee_ngwee: int,
    vendor_id: str,
) -> TemplateResult:
    """Lane 2 change-of-mind refund with deductions.

    Debit escrow (+escrow_release).
    Credit platform_cash (−refund_to_customer).
    Credit vendor_payable (vendor) (−vendor_retained).
    Credit commission_revenue (−restocking_fee).

    Callers must ensure escrow_release = refund_to_customer + vendor_retained + restocking_fee.
    """
    release = parse_ngwee(escrow_release_ngwee)
    refund = parse_ngwee(refund_to_customer_ngwee)
    retained = parse_ngwee(vendor_retained_ngwee)
    restocking = parse_ngwee(restocking_fee_ngwee)
    if release != refund + retained + restocking:
        msg = "escrow_release must equal refund + vendor_retained + restocking_fee"
        raise ValueError(msg)
    legs = (
        PostingLeg(AccountRef("escrow"), release),
        PostingLeg(AccountRef("platform_cash"), -refund),
        PostingLeg(AccountRef("vendor_payable", vendor_id), -retained),
        PostingLeg(AccountRef("commission_revenue"), -restocking),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.REFUND_LANE2, legs=legs)


def cod_collected(*, collected_ngwee: int, vendor_id: str) -> TemplateResult:
    """COD cash collected at delivery — clear vendor COD receivable.

    Debit platform_cash (+collected).
    Credit cod_receivable (vendor) (−collected).
    """
    collected = parse_ngwee(collected_ngwee)
    legs = (
        PostingLeg(AccountRef("platform_cash"), collected),
        PostingLeg(AccountRef("cod_receivable", vendor_id), -collected),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.COD_COLLECTED, legs=legs)


def clawback(*, clawback_ngwee: int, vendor_id: str) -> TemplateResult:
    """Post-release refund clawback — recover funds from vendor payable.

    Debit vendor_payable (vendor) (+clawback).
    Credit platform_cash (−clawback).
    """
    amount = parse_ngwee(clawback_ngwee)
    legs = (
        PostingLeg(AccountRef("vendor_payable", vendor_id), amount),
        PostingLeg(AccountRef("platform_cash"), -amount),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.CLAWBACK, legs=legs)


TemplateFn = Callable[..., TemplateResult]

TEMPLATE_REGISTRY: dict[LedgerTemplate, TemplateFn] = {
    LedgerTemplate.CHARGE_RECEIVED: charge_received,
    LedgerTemplate.ESCROW_HOLD: escrow_hold,
    LedgerTemplate.COMMISSION_CAPTURE: commission_capture,
    LedgerTemplate.RELEASE_TO_VENDOR: release_to_vendor,
    LedgerTemplate.PAYOUT_EXECUTED: payout_executed,
    LedgerTemplate.REFUND_LANE1: refund_lane1,
    LedgerTemplate.REFUND_LANE2: refund_lane2,
    LedgerTemplate.COD_COLLECTED: cod_collected,
    LedgerTemplate.CLAWBACK: clawback,
}

ALL_TEMPLATES: tuple[LedgerTemplate, ...] = tuple(LedgerTemplate)
