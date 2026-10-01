"""Pure, fail-closed inputs for provider/account reconciliation.

This module deliberately does not perform HTTP, database, payout-eligibility, or
refund-entitlement work.  It is the reviewable F3 seam that a later integration
can feed from the accepted F1/F2 runtime.  Missing evidence remains missing.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class EvidenceOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    SOURCE = "source"
    LOCAL = "local"
    CI = "ci"
    SANDBOX_PROVIDER = "sandbox_provider"
    STAGING_CONTROLLED = "staging_controlled"
    STAGING_PROVIDER = "staging_provider"
    PRODUCTION_PROVIDER = "production_provider"


class EvidenceVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIP = "SKIP"
    XFAIL = "XFAIL"
    NOT_RUN = "NOT_RUN"


class MovementDirection(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class MovementKind(StrEnum):
    OPENING_FUNDING = "opening_funding"
    COLLECTION = "collection"
    SERVICE_DEPOSIT = "service_deposit"
    SERVICE_BALANCE = "service_balance"
    SETTLEMENT = "settlement"
    PROVIDER_FEE = "provider_fee"
    VENDOR_PAYOUT = "vendor_payout"
    REFUND_PAYOUT = "refund_payout"
    COLLECTION_EXCEPTION = "collection_exception"
    REVERSAL = "reversal"
    DISPUTE = "dispute"
    UNKNOWN = "unknown"


class CreditBasis(StrEnum):
    GROSS = "gross"
    NET_OF_FEES = "net_of_fees"


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_id: str
    currency: str
    available_balance_ngwee: int
    ledger_balance_ngwee: int


def select_configured_account(
    accounts: Sequence[AccountSnapshot],
    *,
    configured_account_id: str,
    currency: str,
) -> AccountSnapshot:
    """Return exactly the configured account; never fall back to the first row."""
    if not configured_account_id:
        raise ValueError("configured account id is required")
    matches = [row for row in accounts if row.account_id == configured_account_id]
    if len(matches) != 1:
        raise ValueError(
            f"configured account must match exactly once: {configured_account_id!r} "
            f"matched {len(matches)} rows"
        )
    selected = matches[0]
    if selected.currency != currency:
        raise ValueError(
            f"configured account currency mismatch: expected {currency!r}, "
            f"observed {selected.currency!r}"
        )
    return selected


def require_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != normalized.utcoffset():
        raise ValueError(f"{field_name} must use UTC, not a local offset")
    return normalized


@dataclass(frozen=True, slots=True)
class ProviderMovement:
    movement_id: str
    account_id: str
    currency: str
    amount_ngwee: int
    direction: MovementDirection
    kind: MovementKind
    observed_at: datetime
    merchant_reference: str | None = None
    provider_reference: str | None = None
    provider_reference_source: str | None = None
    running_balance_ngwee: int | None = None
    settlement_id: str | None = None
    status: str | None = None
    actor_id: str | None = None
    rail: str | None = None
    leg: str | None = None
    evidence_origin: EvidenceOrigin = EvidenceOrigin.SYNTHETIC

    def __post_init__(self) -> None:
        if not self.movement_id:
            raise ValueError("provider movement id is required")
        if not self.account_id:
            raise ValueError("provider account id is required")
        if self.amount_ngwee < 0:
            raise ValueError("provider amount must be unsigned integer ngwee")
        require_utc(self.observed_at, field_name="provider observed_at")

    @property
    def signed_amount_ngwee(self) -> int:
        return (
            self.amount_ngwee if self.direction == MovementDirection.CREDIT else -self.amount_ngwee
        )


@dataclass(frozen=True, slots=True)
class ProviderPage:
    page_number: int
    cursor: str | None
    next_cursor: str | None
    page_count: int | None
    total: int | None
    movements: tuple[ProviderMovement, ...]
    error: str | None = None
    raw_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PageCollection:
    movements: tuple[ProviderMovement, ...]
    late_movements: tuple[ProviderMovement, ...]
    duplicate_ids: tuple[str, ...]
    issues: tuple[str, ...]
    observed_page_numbers: tuple[int, ...]
    stop_reason: str

    @property
    def complete(self) -> bool:
        return not self.issues


def collect_provider_pages(
    pages: Sequence[ProviderPage],
    *,
    configured_account_id: str,
    currency: str,
    cutoff_utc: datetime,
) -> PageCollection:
    """Validate a complete cursor/page walk and dedupe only identical stable IDs."""
    cutoff = require_utc(cutoff_utc, field_name="cutoff_utc")
    issues: list[str] = []
    duplicate_ids: list[str] = []
    observed_by_id: dict[str, ProviderMovement] = {}
    page_numbers = [page.page_number for page in pages]

    if not pages:
        issues.append("no provider transaction pages were observed")
        return PageCollection((), (), (), tuple(issues), (), "no_pages")

    if page_numbers != list(range(1, len(pages) + 1)):
        issues.append(f"provider pages are missing, repeated, or out of order: {page_numbers!r}")

    missing_page_meta = [
        page.page_number
        for page in pages
        if page.page_count is None or page.total is None
    ]
    if missing_page_meta:
        issues.append(
            "provider pagination metadata missing for pages "
            f"{missing_page_meta!r}"
        )

    declared_counts = {page.page_count for page in pages if page.page_count is not None}
    if len(declared_counts) > 1:
        issues.append(f"provider page_count changed during collection: {sorted(declared_counts)!r}")
    elif declared_counts and next(iter(declared_counts)) != len(pages):
        issues.append(
            f"provider page walk incomplete: declared {next(iter(declared_counts))}, "
            f"observed {len(pages)}"
        )

    # The documented Lenco v2 transaction envelope is page-number based.  Some
    # provider exports also expose cursors, so validate a cursor chain only when
    # the provider actually supplied one.  Never invent a cursor from a page
    # number merely to make an observation look complete.
    has_cursor_evidence = any(
        page.cursor is not None or page.next_cursor is not None for page in pages
    )
    if has_cursor_evidence:
        cursors = [page.cursor for page in pages if page.cursor is not None]
        repeated_cursors = sorted(
            value for value, count in Counter(cursors).items() if count > 1
        )
        if repeated_cursors:
            issues.append(f"provider cursor repeated: {repeated_cursors!r}")

        for current, following in zip(pages, pages[1:], strict=False):
            if current.next_cursor is None:
                issues.append(f"page {current.page_number} ended before a following page")
            elif current.next_cursor != following.cursor:
                issues.append(
                    f"cursor chain mismatch after page {current.page_number}: "
                    f"expected {current.next_cursor!r}, observed {following.cursor!r}"
                )
        if pages[-1].next_cursor is not None:
            issues.append("final provider page advertised an uncollected next cursor")

    totals = {page.total for page in pages if page.total is not None}
    if len(totals) > 1:
        issues.append(f"provider total changed during collection: {sorted(totals)!r}")

    for page in pages:
        if page.error:
            issues.append(f"provider page {page.page_number} failed: {page.error}")
        for movement in page.movements:
            if movement.account_id != configured_account_id:
                issues.append(
                    f"movement {movement.movement_id} belongs to account "
                    f"{movement.account_id!r}, not configured account {configured_account_id!r}"
                )
            if movement.currency != currency:
                issues.append(
                    f"movement {movement.movement_id} currency {movement.currency!r} "
                    f"does not match {currency!r}"
                )
            prior = observed_by_id.get(movement.movement_id)
            if prior is None:
                observed_by_id[movement.movement_id] = movement
            elif prior == movement:
                duplicate_ids.append(movement.movement_id)
            else:
                issues.append(
                    f"conflicting duplicate provider movement id {movement.movement_id!r}"
                )

    if totals:
        declared_total = next(iter(totals))
        observed_raw = sum(len(page.movements) for page in pages)
        if declared_total != observed_raw:
            issues.append(
                f"provider total mismatch: declared {declared_total}, observed {observed_raw} rows"
            )

    retained = {
        movement_id: movement
        for movement_id, movement in observed_by_id.items()
        if movement.observed_at <= cutoff
    }
    late = tuple(
        movement
        for movement_id, movement in sorted(observed_by_id.items())
        if movement.observed_at > cutoff
    )
    stop_reason = "complete" if not issues else "incomplete"
    return PageCollection(
        movements=tuple(retained[key] for key in sorted(retained)),
        late_movements=late,
        duplicate_ids=tuple(sorted(set(duplicate_ids))),
        issues=tuple(issues),
        observed_page_numbers=tuple(page_numbers),
        stop_reason=stop_reason,
    )


@dataclass(frozen=True, slots=True)
class LocalMovement:
    local_id: str
    movement_group: str
    kind: MovementKind
    amount_ngwee: int
    provider_transaction_id: str | None = None
    merchant_reference: str | None = None
    provider_reference: str | None = None
    payment_id: str | None = None
    payout_id: str | None = None
    refund_id: str | None = None
    checkout_id: str | None = None
    order_id: str | None = None
    job_id: str | None = None
    obligation_id: str | None = None
    collection_exception_id: str | None = None
    ledger_transaction_id: str | None = None
    ledger_linkage_id: str | None = None
    allocation_id: str | None = None
    actor_id: str | None = None
    rail: str | None = None
    leg: str | None = None

    def __post_init__(self) -> None:
        if not self.local_id or not self.movement_group:
            raise ValueError("local movement identity and group are required")
        domain_linkages = {
            value
            for value in (
                self.payment_id,
                self.payout_id,
                self.refund_id,
                self.checkout_id,
                self.order_id,
                self.job_id,
                self.obligation_id,
                self.collection_exception_id,
            )
            if value
        }
        if (
            self.ledger_transaction_id
            and not self.ledger_linkage_id
            and self.kind != MovementKind.UNKNOWN
        ):
            raise ValueError(f"local movement {self.local_id!r} has no ledger linkage evidence")
        if self.ledger_linkage_id and self.ledger_linkage_id not in domain_linkages:
            raise ValueError(
                f"local movement {self.local_id!r} has incorrect ledger linkage "
                f"{self.ledger_linkage_id!r}"
            )


@dataclass(frozen=True, slots=True)
class AggregatedLocalMovement:
    movement_group: str
    kind: MovementKind
    amount_ngwee: int
    provider_transaction_id: str | None
    merchant_reference: str | None
    provider_reference: str | None
    local_ids: tuple[str, ...]
    ledger_transaction_ids: tuple[str, ...]
    ledger_linkage_ids: tuple[str, ...]
    allocation_ids: tuple[str, ...]
    actor_ids: tuple[str, ...]
    rails: tuple[str, ...]
    legs: tuple[str, ...]
    linkage_ids: tuple[str, ...]


def _one_or_none(values: Sequence[str], *, group: str, field_name: str) -> str | None:
    unique = sorted(set(values))
    if len(unique) > 1:
        raise ValueError(f"local group {group!r} has conflicting {field_name}: {unique!r}")
    return unique[0] if unique else None


def aggregate_local_movements(rows: Sequence[LocalMovement]) -> tuple[AggregatedLocalMovement, ...]:
    """Aggregate allocations while retaining every local identity and unparsed row."""
    grouped: dict[str, list[LocalMovement]] = defaultdict(list)
    for row in rows:
        grouped[row.movement_group].append(row)

    output: list[AggregatedLocalMovement] = []
    for group in sorted(grouped):
        members = grouped[group]
        kinds = {member.kind for member in members}
        if len(kinds) != 1:
            raise ValueError(f"local group {group!r} mixes movement kinds")
        linkages: set[str] = set()
        for member in members:
            linkages.update(
                value
                for value in (
                    member.payment_id,
                    member.payout_id,
                    member.refund_id,
                    member.checkout_id,
                    member.order_id,
                    member.job_id,
                    member.obligation_id,
                    member.collection_exception_id,
                )
                if value
            )
        output.append(
            AggregatedLocalMovement(
                movement_group=group,
                kind=next(iter(kinds)),
                amount_ngwee=sum(member.amount_ngwee for member in members),
                provider_transaction_id=_one_or_none(
                    [
                        member.provider_transaction_id
                        for member in members
                        if member.provider_transaction_id
                    ],
                    group=group,
                    field_name="provider transaction ids",
                ),
                merchant_reference=_one_or_none(
                    [member.merchant_reference for member in members if member.merchant_reference],
                    group=group,
                    field_name="merchant references",
                ),
                provider_reference=_one_or_none(
                    [member.provider_reference for member in members if member.provider_reference],
                    group=group,
                    field_name="provider references",
                ),
                local_ids=tuple(sorted(member.local_id for member in members)),
                ledger_transaction_ids=tuple(
                    sorted(
                        member.ledger_transaction_id
                        for member in members
                        if member.ledger_transaction_id
                    )
                ),
                ledger_linkage_ids=tuple(
                    sorted(
                        member.ledger_linkage_id for member in members if member.ledger_linkage_id
                    )
                ),
                allocation_ids=tuple(
                    sorted(member.allocation_id for member in members if member.allocation_id)
                ),
                actor_ids=tuple(sorted({member.actor_id for member in members if member.actor_id})),
                rails=tuple(sorted({member.rail for member in members if member.rail})),
                legs=tuple(sorted({member.leg for member in members if member.leg})),
                linkage_ids=tuple(sorted(linkages)),
            )
        )
    return tuple(output)


@dataclass(frozen=True, slots=True)
class MovementMatch:
    provider_movement_id: str
    local_movement_group: str
    identity_kind: str
    provider_amount_ngwee: int
    local_amount_ngwee: int
    difference_ngwee: int


@dataclass(frozen=True, slots=True)
class MatchIssue:
    identity: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchReport:
    matches: tuple[MovementMatch, ...]
    provider_unmatched: tuple[MatchIssue, ...]
    local_unmatched: tuple[MatchIssue, ...]
    ambiguous: tuple[MatchIssue, ...]

    @property
    def exact(self) -> bool:
        return (
            not self.provider_unmatched
            and not self.local_unmatched
            and not self.ambiguous
            and all(match.difference_ngwee == 0 for match in self.matches)
        )


def _index_groups(
    rows: Sequence[AggregatedLocalMovement], field_name: str
) -> dict[str, tuple[str, ...]]:
    indexed: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        value = getattr(row, field_name)
        if isinstance(value, str) and value:
            indexed[value].append(row.movement_group)
    return {key: tuple(sorted(value)) for key, value in indexed.items()}


def match_movements(
    provider_rows: Sequence[ProviderMovement],
    local_rows: Sequence[LocalMovement],
) -> MatchReport:
    """Match by stable identities; free-text narration is never a join key."""
    local = aggregate_local_movements(local_rows)
    by_group = {row.movement_group: row for row in local}
    by_provider_id = _index_groups(local, "provider_transaction_id")
    by_provider_ref = _index_groups(local, "provider_reference")
    by_merchant_ref = _index_groups(local, "merchant_reference")
    provider_ref_counts = Counter(
        row.provider_reference for row in provider_rows if row.provider_reference
    )
    merchant_ref_counts = Counter(
        row.merchant_reference for row in provider_rows if row.merchant_reference
    )

    matches: list[MovementMatch] = []
    provider_unmatched: list[MatchIssue] = []
    ambiguous: list[MatchIssue] = []
    used_groups: set[str] = set()

    for provider in sorted(provider_rows, key=lambda row: row.movement_id):
        identity_kind = ""
        identity = ""
        candidates: tuple[str, ...] = ()
        if provider.movement_id in by_provider_id:
            identity_kind = "provider_transaction_id"
            identity = provider.movement_id
            candidates = by_provider_id[identity]
        elif provider.provider_reference and provider.provider_reference in by_provider_ref:
            identity_kind = "provider_reference"
            identity = provider.provider_reference
            candidates = by_provider_ref[identity]
            if provider_ref_counts[identity] > 1:
                ambiguous.append(
                    MatchIssue(
                        identity, "provider reference maps multiple distinct movements", candidates
                    )
                )
                continue
        elif provider.merchant_reference and provider.merchant_reference in by_merchant_ref:
            identity_kind = "merchant_reference"
            identity = provider.merchant_reference
            candidates = by_merchant_ref[identity]
            if merchant_ref_counts[identity] > 1:
                ambiguous.append(
                    MatchIssue(
                        identity, "merchant reference maps multiple distinct movements", candidates
                    )
                )
                continue
        else:
            visible = (
                provider.provider_reference or provider.merchant_reference or provider.movement_id
            )
            reason = (
                "provider movement has no mapped reference"
                if not provider.provider_reference and not provider.merchant_reference
                else "no local movement matched provider identity"
            )
            provider_unmatched.append(MatchIssue(visible, reason))
            continue

        if len(candidates) != 1:
            ambiguous.append(MatchIssue(identity, "local identity is ambiguous", candidates))
            continue
        group = candidates[0]
        if group in used_groups:
            ambiguous.append(
                MatchIssue(
                    identity,
                    "local movement would be consumed by multiple provider movements",
                    (group,),
                )
            )
            continue
        local_row = by_group[group]
        used_groups.add(group)
        matches.append(
            MovementMatch(
                provider_movement_id=provider.movement_id,
                local_movement_group=group,
                identity_kind=identity_kind,
                provider_amount_ngwee=provider.signed_amount_ngwee,
                local_amount_ngwee=local_row.amount_ngwee,
                difference_ngwee=provider.signed_amount_ngwee - local_row.amount_ngwee,
            )
        )

    local_unmatched = [
        MatchIssue(row.movement_group, "local movement has no matched provider movement")
        for row in local
        if row.movement_group not in used_groups
    ]
    return MatchReport(
        matches=tuple(matches),
        provider_unmatched=tuple(provider_unmatched),
        local_unmatched=tuple(local_unmatched),
        ambiguous=tuple(ambiguous),
    )


@dataclass(frozen=True, slots=True)
class FeeEvidence:
    fee_id: str
    source_movement_id: str
    amount_ngwee: int | None
    reversed_ngwee: int = 0
    previously_recovered_ngwee: int = 0
    recoverability_evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class BalanceBridgeInput:
    account_id: str
    currency: str
    statement_id: str
    statement_source_hash: str
    statement_cutoff_utc: datetime
    opening_funds_ngwee: int
    settled_credits_ngwee: int
    successful_outgoing_transfers_ngwee: int
    successful_refunds_ngwee: int
    evidenced_reversals_ngwee: int
    unsettled_credits_ngwee: int
    disputed_positions_ngwee: int
    observed_ledger_balance_ngwee: int
    observed_available_balance_ngwee: int
    credit_basis: CreditBasis
    fees: tuple[FeeEvidence, ...]


@dataclass(frozen=True, slots=True)
class BalanceBridge:
    account_id: str
    currency: str
    statement_id: str
    statement_source_hash: str
    statement_cutoff_utc: datetime
    opening_funds_ngwee: int
    settled_credits_ngwee: int
    fees_subtracted_ngwee: int
    successful_outgoing_transfers_ngwee: int
    successful_refunds_ngwee: int
    evidenced_reversals_ngwee: int
    unsettled_credits_ngwee: int
    disputed_positions_ngwee: int
    expected_ledger_balance_ngwee: int
    observed_ledger_balance_ngwee: int
    ledger_difference_ngwee: int
    expected_available_balance_ngwee: int
    observed_available_balance_ngwee: int
    available_difference_ngwee: int
    unresolved: tuple[str, ...]

    @property
    def exact(self) -> bool:
        return (
            not self.unresolved
            and self.ledger_difference_ngwee == 0
            and self.available_difference_ngwee == 0
        )


def build_balance_bridge(
    value: BalanceBridgeInput,
    *,
    configured_account_id: str,
    currency: str,
) -> BalanceBridge:
    """Bridge one immutable provider statement against the configured account."""
    if value.account_id != configured_account_id:
        raise ValueError(
            f"statement account mismatch: expected {configured_account_id!r}, "
            f"observed {value.account_id!r}"
        )
    if value.currency != currency:
        raise ValueError(
            f"statement currency mismatch: expected {currency!r}, observed {value.currency!r}"
        )
    if not value.statement_id or not value.statement_source_hash:
        raise ValueError("statement identity and source hash are required")
    statement_cutoff = require_utc(
        value.statement_cutoff_utc,
        field_name="statement_cutoff_utc",
    )
    unresolved: list[str] = []
    fees_subtracted = 0
    seen_fee_ids: set[str] = set()
    for fee in value.fees:
        if fee.fee_id in seen_fee_ids:
            unresolved.append(f"duplicate fee identity {fee.fee_id!r}")
            continue
        seen_fee_ids.add(fee.fee_id)
        if fee.amount_ngwee is None:
            unresolved.append(f"fee {fee.fee_id!r} has no amount evidence")
            continue
        if fee.amount_ngwee < 0 or fee.reversed_ngwee < 0:
            unresolved.append(f"fee {fee.fee_id!r} contains a negative component")
            continue
        if fee.reversed_ngwee > fee.amount_ngwee:
            unresolved.append(f"fee {fee.fee_id!r} reversal exceeds the evidenced fee")
            continue
        if value.credit_basis == CreditBasis.GROSS:
            fees_subtracted += fee.amount_ngwee - fee.reversed_ngwee

    expected_ledger = (
        value.opening_funds_ngwee
        + value.settled_credits_ngwee
        - fees_subtracted
        - value.successful_outgoing_transfers_ngwee
        - value.successful_refunds_ngwee
        + value.evidenced_reversals_ngwee
    )
    expected_available = expected_ledger - value.disputed_positions_ngwee
    return BalanceBridge(
        account_id=value.account_id,
        currency=value.currency,
        statement_id=value.statement_id,
        statement_source_hash=value.statement_source_hash,
        statement_cutoff_utc=statement_cutoff,
        opening_funds_ngwee=value.opening_funds_ngwee,
        settled_credits_ngwee=value.settled_credits_ngwee,
        fees_subtracted_ngwee=fees_subtracted,
        successful_outgoing_transfers_ngwee=value.successful_outgoing_transfers_ngwee,
        successful_refunds_ngwee=value.successful_refunds_ngwee,
        evidenced_reversals_ngwee=value.evidenced_reversals_ngwee,
        unsettled_credits_ngwee=value.unsettled_credits_ngwee,
        disputed_positions_ngwee=value.disputed_positions_ngwee,
        expected_ledger_balance_ngwee=expected_ledger,
        observed_ledger_balance_ngwee=value.observed_ledger_balance_ngwee,
        ledger_difference_ngwee=value.observed_ledger_balance_ngwee - expected_ledger,
        expected_available_balance_ngwee=expected_available,
        observed_available_balance_ngwee=value.observed_available_balance_ngwee,
        available_difference_ngwee=value.observed_available_balance_ngwee - expected_available,
        unresolved=tuple(unresolved),
    )


@dataclass(frozen=True, slots=True)
class CostEvidenceCalculation:
    refundable_paid_ngwee: int
    proposed_ceiling_ngwee: int
    evidenced_unrecovered_cost_ngwee: int | None
    proposed_deduction_ngwee: int | None
    proposed_refund_ngwee: int | None
    unresolved: tuple[str, ...]
    enabled: bool = False


def calculate_proposed_cost_evidence(
    *,
    refundable_paid_ngwee: int,
    actual_attributable_cost_ngwee: int | None,
    previously_recovered_ngwee: int = 0,
    ceiling_bps: int = 500,
    policy_eligible: bool,
    mandatory_zero_reason: str | None = None,
) -> CostEvidenceCalculation:
    """Calculate the Q5 proposal without enabling a deduction or deciding entitlement."""
    if (
        refundable_paid_ngwee < 0
        or previously_recovered_ngwee < 0
        or (actual_attributable_cost_ngwee is not None and actual_attributable_cost_ngwee < 0)
    ):
        raise ValueError("cost evidence inputs must be non-negative integer ngwee")
    if not 0 <= ceiling_bps <= 10_000:
        raise ValueError("ceiling_bps must be between 0 and 10000")
    ceiling = refundable_paid_ngwee * ceiling_bps // 10_000
    if mandatory_zero_reason is not None or not policy_eligible:
        return CostEvidenceCalculation(
            refundable_paid_ngwee,
            ceiling,
            0,
            0,
            refundable_paid_ngwee,
            (),
        )
    if actual_attributable_cost_ngwee is None:
        return CostEvidenceCalculation(
            refundable_paid_ngwee,
            ceiling,
            None,
            None,
            None,
            ("actual attributable provider cost is unresolved",),
        )
    unrecovered = max(0, actual_attributable_cost_ngwee - previously_recovered_ngwee)
    deduction = min(ceiling, unrecovered)
    return CostEvidenceCalculation(
        refundable_paid_ngwee,
        ceiling,
        unrecovered,
        deduction,
        refundable_paid_ngwee - deduction,
        (),
    )


@dataclass(frozen=True, slots=True)
class PayoutDecisionEvidence:
    obligation_id: str
    account_id: str
    currency: str
    snapshot_at: datetime
    released_liability_ngwee: int
    available_balance_ngwee: int
    active_holds_ngwee: int | None
    kyc_evidence_id: str | None
    immutable_destination_fingerprint: str | None
    dispatch_claim_id: str | None
    provider_settlement_evidence_id: str | None
    order_release_evidence_id: str | None


def payout_decision_evidence_gaps(value: PayoutDecisionEvidence) -> tuple[str, ...]:
    """Expose Q6 inputs only; this function never authorizes a payout."""
    require_utc(value.snapshot_at, field_name="payout snapshot_at")
    gaps: list[str] = []
    if not value.obligation_id:
        gaps.append("obligation identity missing")
    if not value.account_id:
        gaps.append("configured provider account identity missing")
    if value.currency != "ZMW":
        gaps.append("provider account currency is not ZMW")
    if value.active_holds_ngwee is None:
        gaps.append("active holds are unresolved")
    for field_name, field_value in (
        ("KYC evidence", value.kyc_evidence_id),
        ("immutable destination", value.immutable_destination_fingerprint),
        ("dispatch claim", value.dispatch_claim_id),
        ("provider settlement", value.provider_settlement_evidence_id),
        ("order release", value.order_release_evidence_id),
    ):
        if not field_value:
            gaps.append(f"{field_name} missing")
    if value.available_balance_ngwee < value.released_liability_ngwee:
        gaps.append("configured account availability is below this obligation")
    return tuple(gaps)


@dataclass(frozen=True, slots=True)
class AcceptanceEvidenceRow:
    case_id: int
    verdict: EvidenceVerdict
    origin: EvidenceOrigin
    candidate_sha: str
    deployment_id: str
    schema_id: str
    observed_at: datetime
    actor_id: str | None = None
    rail: str | None = None
    leg: str | None = None
    account_id: str | None = None
    merchant_reference: str | None = None
    provider_reference: str | None = None
    provider_transaction_id: str | None = None
    receipt_id: str | None = None
    checkout_id: str | None = None
    order_id: str | None = None
    job_id: str | None = None
    obligation_id: str | None = None
    payout_id: str | None = None
    refund_id: str | None = None
    collection_exception_id: str | None = None
    report_version: str | None = None
    ledger_transaction_ids: tuple[str, ...] = ()
    simulated: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    required_fields: tuple[str, ...]
    provider_required: bool


_COMMON_PROVIDER = ("actor_id", "rail", "merchant_reference", "provider_reference")
ACCEPTANCE_REQUIREMENTS: Mapping[int, EvidenceRequirement] = {
    1: EvidenceRequirement(
        _COMMON_PROVIDER + ("receipt_id", "checkout_id", "ledger_transaction_ids"), True
    ),
    2: EvidenceRequirement(
        _COMMON_PROVIDER + ("receipt_id", "checkout_id", "ledger_transaction_ids"), True
    ),
    3: EvidenceRequirement(_COMMON_PROVIDER + ("provider_transaction_id",), True),
    4: EvidenceRequirement(_COMMON_PROVIDER + ("provider_transaction_id",), True),
    5: EvidenceRequirement(_COMMON_PROVIDER + ("receipt_id", "ledger_transaction_ids"), True),
    6: EvidenceRequirement(("actor_id", "rail", "checkout_id"), False),
    7: EvidenceRequirement(_COMMON_PROVIDER + ("receipt_id", "ledger_transaction_ids"), True),
    8: EvidenceRequirement(_COMMON_PROVIDER + ("checkout_id",), True),
    9: EvidenceRequirement(_COMMON_PROVIDER + ("receipt_id", "ledger_transaction_ids"), True),
    10: EvidenceRequirement(("actor_id", "rail", "checkout_id"), False),
    11: EvidenceRequirement(
        _COMMON_PROVIDER + ("receipt_id", "order_id", "ledger_transaction_ids"), True
    ),
    12: EvidenceRequirement(
        _COMMON_PROVIDER
        + ("leg", "receipt_id", "job_id", "obligation_id", "ledger_transaction_ids"),
        True,
    ),
    13: EvidenceRequirement(
        _COMMON_PROVIDER + ("receipt_id", "order_id", "ledger_transaction_ids"), True
    ),
    14: EvidenceRequirement(("actor_id", "rail", "checkout_id", "order_id"), False),
    15: EvidenceRequirement(_COMMON_PROVIDER + ("collection_exception_id", "order_id"), True),
    16: EvidenceRequirement(
        _COMMON_PROVIDER + ("refund_id", "payout_id", "ledger_transaction_ids"), True
    ),
    17: EvidenceRequirement(_COMMON_PROVIDER + ("payout_id", "ledger_transaction_ids"), True),
    18: EvidenceRequirement(_COMMON_PROVIDER + ("payout_id",), True),
    19: EvidenceRequirement(("account_id", "report_version", "ledger_transaction_ids"), True),
    20: EvidenceRequirement(_COMMON_PROVIDER + ("receipt_id", "ledger_transaction_ids"), True),
    21: EvidenceRequirement(("account_id", "report_version", "ledger_transaction_ids"), True),
    22: EvidenceRequirement(("actor_id", "leg", "order_id", "ledger_transaction_ids"), True),
    23: EvidenceRequirement(("actor_id", "leg", "order_id", "ledger_transaction_ids"), True),
    24: EvidenceRequirement(
        ("account_id", "report_version", "provider_transaction_id", "ledger_transaction_ids"), True
    ),
}


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    expected_count: int
    observed_count: int
    passed_count: int
    issues: tuple[str, ...]

    @property
    def certifiable(self) -> bool:
        return (
            self.observed_count == self.expected_count
            and self.passed_count == self.expected_count
            and not self.issues
        )


def _has_evidence_value(row: AcceptanceEvidenceRow, field_name: str) -> bool:
    value = getattr(row, field_name)
    if isinstance(value, tuple):
        return bool(value)
    return value is not None and value != ""


def assess_acceptance_evidence(rows: Sequence[AcceptanceEvidenceRow]) -> EvidenceAssessment:
    """Require 24 explicit source-bound rows; aggregate totals are not evidence."""
    issues: list[str] = []
    by_id: dict[int, AcceptanceEvidenceRow] = {}
    for row in rows:
        if row.case_id in by_id:
            issues.append(f"duplicate acceptance case {row.case_id}")
            continue
        by_id[row.case_id] = row

    expected = set(ACCEPTANCE_REQUIREMENTS)
    missing = sorted(expected - set(by_id))
    unexpected = sorted(set(by_id) - expected)
    if missing:
        issues.append(f"missing acceptance cases {missing!r}")
    if unexpected:
        issues.append(f"unexpected acceptance cases {unexpected!r}")

    passed = 0
    provider_origins = {
        EvidenceOrigin.SANDBOX_PROVIDER,
        EvidenceOrigin.STAGING_PROVIDER,
        EvidenceOrigin.PRODUCTION_PROVIDER,
    }
    runtime_origins = provider_origins | {EvidenceOrigin.STAGING_CONTROLLED}
    for case_id in sorted(expected & set(by_id)):
        row = by_id[case_id]
        requirement = ACCEPTANCE_REQUIREMENTS[case_id]
        require_utc(row.observed_at, field_name=f"case {case_id} observed_at")
        if row.verdict != EvidenceVerdict.PASS:
            issues.append(f"case {case_id} verdict is {row.verdict.value}, not PASS")
            continue
        if not row.candidate_sha or not row.deployment_id or not row.schema_id:
            issues.append(f"case {case_id} is not bound to candidate/deployment/schema")
        if row.origin not in runtime_origins:
            issues.append(f"case {case_id} uses non-runtime origin {row.origin.value!r}")
        if requirement.provider_required and row.origin not in provider_origins:
            issues.append(f"case {case_id} lacks provider-origin evidence")
        if row.simulated:
            issues.append(f"case {case_id} is explicitly simulated")
        missing_fields = [
            field_name
            for field_name in requirement.required_fields
            if not _has_evidence_value(row, field_name)
        ]
        if missing_fields:
            issues.append(f"case {case_id} missing required evidence {missing_fields!r}")
        if not any(issue.startswith(f"case {case_id} ") for issue in issues):
            passed += 1

    return EvidenceAssessment(len(expected), len(by_id), passed, tuple(issues))


def _optional_text(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"acceptance evidence field {key!r} must be text or null")
    return value or None


def parse_acceptance_evidence_rows(payload: object) -> tuple[AcceptanceEvidenceRow, ...]:
    """Parse the versioned 24-row JSON contract without inventing absent fields."""
    if not isinstance(payload, Mapping):
        raise ValueError("acceptance evidence payload must be an object")
    raw_rows = payload.get("acceptance_rows")
    if not isinstance(raw_rows, list):
        raise ValueError("acceptance_rows must be an array")
    rows: list[AcceptanceEvidenceRow] = []
    for index, value in enumerate(raw_rows):
        if not isinstance(value, Mapping):
            raise ValueError(f"acceptance row {index} must be an object")
        observed_at_raw = value.get("observed_at")
        if not isinstance(observed_at_raw, str):
            raise ValueError(f"acceptance row {index} observed_at must be an ISO-8601 string")
        ledger_raw = value.get("ledger_transaction_ids", [])
        if not isinstance(ledger_raw, list) or not all(
            isinstance(item, str) and item for item in ledger_raw
        ):
            raise ValueError(
                f"acceptance row {index} ledger_transaction_ids must contain nonempty strings"
            )
        case_id = value.get("case_id")
        simulated = value.get("simulated")
        if not isinstance(case_id, int) or isinstance(case_id, bool):
            raise ValueError(f"acceptance row {index} case_id must be an integer")
        if not isinstance(simulated, bool):
            raise ValueError(f"acceptance row {index} simulated must be boolean")
        try:
            verdict = EvidenceVerdict(str(value["verdict"]))
            origin = EvidenceOrigin(str(value["origin"]))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"acceptance row {index} has an invalid verdict/origin") from exc
        rows.append(
            AcceptanceEvidenceRow(
                case_id=case_id,
                verdict=verdict,
                origin=origin,
                candidate_sha=_optional_text(value, "candidate_sha") or "",
                deployment_id=_optional_text(value, "deployment_id") or "",
                schema_id=_optional_text(value, "schema_id") or "",
                observed_at=datetime.fromisoformat(observed_at_raw),
                actor_id=_optional_text(value, "actor_id"),
                rail=_optional_text(value, "rail"),
                leg=_optional_text(value, "leg"),
                account_id=_optional_text(value, "account_id"),
                merchant_reference=_optional_text(value, "merchant_reference"),
                provider_reference=_optional_text(value, "provider_reference"),
                provider_transaction_id=_optional_text(value, "provider_transaction_id"),
                receipt_id=_optional_text(value, "receipt_id"),
                checkout_id=_optional_text(value, "checkout_id"),
                order_id=_optional_text(value, "order_id"),
                job_id=_optional_text(value, "job_id"),
                obligation_id=_optional_text(value, "obligation_id"),
                payout_id=_optional_text(value, "payout_id"),
                refund_id=_optional_text(value, "refund_id"),
                collection_exception_id=_optional_text(value, "collection_exception_id"),
                report_version=_optional_text(value, "report_version"),
                ledger_transaction_ids=tuple(ledger_raw),
                simulated=simulated,
            )
        )
    return tuple(rows)
