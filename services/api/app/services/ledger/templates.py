"""Double-entry posting templates — the sole write path for ledger postings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.schemas.base import parse_ngwee

PLATFORM_ACCOUNT_KINDS = frozenset(
    {
        "platform_cash",
        "escrow",
        "commission_revenue",
        "fees",
        "delivery_revenue",
        "marketing_expense",
    }
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
    REFUND_REVERSAL = "refund_reversal"
    LENCO_FEE = "lenco_fee"
    DELIVERY_FEE_CAPTURE = "delivery_fee_capture"
    COD_COLLECTED_BY_VENDOR = "cod_collected_by_vendor"
    COUPON_FUNDING = "coupon_funding"


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


def _promo_return(promo_return_ngwee: int) -> int:
    """Platform-funded coupon share handed back to marketing_expense (0 = none)."""
    return 0 if promo_return_ngwee == 0 else parse_ngwee(promo_return_ngwee)


def refund_lane1(*, refund_ngwee: int, promo_return_ngwee: int = 0) -> TemplateResult:
    """Lane 1 full refund (faulty/wrong) — return funds from escrow to platform cash.

    Debit escrow (+refund + promo_return).
    Credit platform_cash (−refund) — what the customer actually paid.
    Credit marketing_expense (−promo_return) — the platform-funded coupon share
    that topped escrow up at collection goes back where it came from.
    """
    refund = parse_ngwee(refund_ngwee)
    promo = _promo_return(promo_return_ngwee)
    legs: tuple[PostingLeg, ...] = (
        PostingLeg(AccountRef("escrow"), refund + promo),
        PostingLeg(AccountRef("platform_cash"), -refund),
    )
    if promo:
        legs = (*legs, PostingLeg(AccountRef("marketing_expense"), -promo))
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.REFUND_LANE1, legs=legs)


def refund_lane2(
    *,
    escrow_release_ngwee: int,
    refund_to_customer_ngwee: int,
    vendor_retained_ngwee: int,
    restocking_fee_ngwee: int,
    vendor_id: str,
    promo_return_ngwee: int = 0,
) -> TemplateResult:
    """Lane 2 change-of-mind refund with deductions.

    ``promo_return_ngwee`` (platform-funded coupon share) is drained from escrow
    on top of ``escrow_release`` and credited back to marketing_expense.

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
    promo = _promo_return(promo_return_ngwee)
    candidates = (
        PostingLeg(AccountRef("escrow"), release + promo),
        PostingLeg(AccountRef("platform_cash"), -refund),
        PostingLeg(AccountRef("vendor_payable", vendor_id), -retained),
        PostingLeg(AccountRef("commission_revenue"), -restocking),
        PostingLeg(AccountRef("marketing_expense"), -promo),
    )
    # Zero legs are dropped only for the coupon leg so the legacy shape is unchanged.
    legs = candidates if promo else candidates[:4]
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


def clawback(
    *,
    clawback_ngwee: int,
    vendor_id: str,
    delivery_fee_ngwee: int = 0,
    promo_return_ngwee: int = 0,
) -> TemplateResult:
    """Post-release refund clawback — recover funds from vendor payable.

    Debit vendor_payable (vendor) (+clawback − delivery_fee).
    Debit delivery_revenue (+delivery_fee) — the refunded delivery fee the platform
    captured at release (never vendor money, so never clawed from the vendor).
    Credit platform_cash (−clawback).
    With ``promo_return_ngwee`` (platform-funded coupon share, released to the
    vendor at full price): also debit vendor_payable and credit marketing_expense
    by that share, so the vendor gives back the full item price it received.
    """
    amount = parse_ngwee(clawback_ngwee)
    promo = _promo_return(promo_return_ngwee)
    fee = 0 if delivery_fee_ngwee == 0 else parse_ngwee(delivery_fee_ngwee)
    if fee > amount:
        msg = "delivery_fee_ngwee must not exceed clawback_ngwee"
        raise ValueError(msg)
    vendor_part = amount - fee
    debit_legs: list[PostingLeg] = []
    if vendor_part > 0:
        debit_legs.append(PostingLeg(AccountRef("vendor_payable", vendor_id), vendor_part))
    if fee > 0:
        debit_legs.append(PostingLeg(AccountRef("delivery_revenue"), fee))
    legs = (*debit_legs, PostingLeg(AccountRef("platform_cash"), -amount))
    if promo:
        legs = (
            *legs,
            PostingLeg(AccountRef("vendor_payable", vendor_id), promo),
            PostingLeg(AccountRef("marketing_expense"), -promo),
        )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.CLAWBACK, legs=legs)


def refund_reversal(*, original_legs: tuple[PostingLeg, ...]) -> TemplateResult:
    """Compensating entry for a refund whose customer payout definitively failed.

    Negates every leg of the original refund posting (``refund_lane1`` /
    ``refund_lane2`` / ``clawback``) so escrow / vendor_payable / platform_cash
    return to where they were before the refund decision. The original rows are
    never mutated (immutable ledger) — this is a new balanced transaction.
    """
    if not original_legs:
        msg = "original_legs must not be empty"
        raise ValueError(msg)
    legs = tuple(
        PostingLeg(leg.account, -parse_ngwee_signed(leg.amount_ngwee)) for leg in original_legs
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.REFUND_REVERSAL, legs=legs)


def lenco_fee(*, fee_ngwee: int) -> TemplateResult:
    """Provider fee Lenco deducts from our merchant account (bearer=merchant).

    Debit fees (+fee) — platform expense.
    Credit platform_cash (−fee) — the Lenco balance is lower by the fee.

    Booking this keeps ``platform_cash`` equal to the Lenco available balance so
    the daily reconciliation report can come out clean.
    """
    fee = parse_ngwee(fee_ngwee)
    legs = (
        PostingLeg(AccountRef("fees"), fee),
        PostingLeg(AccountRef("platform_cash"), -fee),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.LENCO_FEE, legs=legs)


def delivery_fee_capture(*, delivery_fee_ngwee: int) -> TemplateResult:
    """Move the customer's delivery fee out of escrow to platform delivery revenue.

    The platform books and pays the courier (D16), so the fee is platform income,
    never part of the vendor's release.

    Debit escrow (+fee).
    Credit delivery_revenue (−fee).
    """
    fee = parse_ngwee(delivery_fee_ngwee)
    if fee <= 0:
        msg = "delivery_fee_ngwee must be positive"
        raise ValueError(msg)
    legs = (
        PostingLeg(AccountRef("escrow"), fee),
        PostingLeg(AccountRef("delivery_revenue"), -fee),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.DELIVERY_FEE_CAPTURE, legs=legs)


def cod_collected_by_vendor(*, collected_ngwee: int, vendor_id: str) -> TemplateResult:
    """COD cash taken by the vendor at its own counter (pickup) — never platform cash.

    The vendor already holds the cash, so it is booked against what the platform
    owes the vendor: after the usual capture + release the vendor's payable shows
    the commission (and any delivery fee) the vendor owes the platform.

    Debit vendor_payable (vendor) (+collected).
    Credit cod_receivable (vendor) (−collected).
    """
    collected = parse_ngwee(collected_ngwee)
    legs = (
        PostingLeg(AccountRef("vendor_payable", vendor_id), collected),
        PostingLeg(AccountRef("cod_receivable", vendor_id), -collected),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.COD_COLLECTED_BY_VENDOR, legs=legs)


def coupon_funding(*, discount_ngwee: int) -> TemplateResult:
    """Platform-funded coupon: top escrow up to the full price at collection.

    Debit marketing_expense (+discount).
    Credit escrow (−discount).
    """
    discount = parse_ngwee(discount_ngwee)
    legs = (
        PostingLeg(AccountRef("marketing_expense"), discount),
        PostingLeg(AccountRef("escrow"), -discount),
    )
    _assert_balanced(legs)
    return TemplateResult(kind=LedgerTemplate.COUPON_FUNDING, legs=legs)


def parse_ngwee_signed(value: int) -> int:
    """Validate a signed (non-zero) integer ngwee posting amount — never float/bool."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "posting amount must be integer ngwee"
        raise TypeError(msg)
    if value == 0:
        msg = "posting amount must be non-zero"
        raise ValueError(msg)
    return value


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
    LedgerTemplate.REFUND_REVERSAL: refund_reversal,
    LedgerTemplate.LENCO_FEE: lenco_fee,
    LedgerTemplate.DELIVERY_FEE_CAPTURE: delivery_fee_capture,
    LedgerTemplate.COD_COLLECTED_BY_VENDOR: cod_collected_by_vendor,
    LedgerTemplate.COUPON_FUNDING: coupon_funding,
}

ALL_TEMPLATES: tuple[LedgerTemplate, ...] = tuple(LedgerTemplate)
