"""F3 pure matcher/harness controls; no provider or database evidence is claimed."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from app.services.payments.reconciliation_matcher import (
    AcceptanceEvidenceRow,
    AccountSnapshot,
    BalanceBridgeInput,
    CreditBasis,
    EvidenceOrigin,
    EvidenceVerdict,
    FeeEvidence,
    LocalMovement,
    MovementDirection,
    MovementKind,
    PayoutDecisionEvidence,
    ProviderMovement,
    ProviderPage,
    aggregate_local_movements,
    assess_acceptance_evidence,
    build_balance_bridge,
    calculate_proposed_cost_evidence,
    collect_provider_pages,
    match_movements,
    parse_acceptance_evidence_rows,
    payout_decision_evidence_gaps,
    select_configured_account,
)

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "drills"
    / "fixtures"
    / "f3_reconciliation_goldens.json"
)


def _fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE.read_text(encoding="utf-8")))


def _dt(value: object) -> datetime:
    assert isinstance(value, str)
    return datetime.fromisoformat(value)


def _movement(raw: dict[str, Any], *, account_id: str, currency: str) -> ProviderMovement:
    return ProviderMovement(
        movement_id=str(raw["movement_id"]),
        account_id=account_id,
        currency=currency,
        amount_ngwee=int(raw["amount_ngwee"]),
        direction=MovementDirection(str(raw["direction"])),
        kind=MovementKind(str(raw["kind"])),
        observed_at=_dt(raw["observed_at"]),
        merchant_reference=cast(str | None, raw.get("merchant_reference")),
        provider_reference=cast(str | None, raw.get("provider_reference")),
        evidence_origin=EvidenceOrigin.SYNTHETIC,
    )


def _pages(payload: dict[str, Any]) -> tuple[ProviderPage, ...]:
    account_id = str(payload["configured_account_id"])
    currency = str(payload["currency"])
    pages: list[ProviderPage] = []
    for page_raw in cast(list[dict[str, Any]], payload["provider_pages"]):
        pages.append(
            ProviderPage(
                page_number=int(page_raw["page_number"]),
                cursor=cast(str | None, page_raw.get("cursor")),
                next_cursor=cast(str | None, page_raw.get("next_cursor")),
                page_count=int(page_raw["page_count"]),
                total=int(page_raw["total"]),
                movements=tuple(
                    _movement(item, account_id=account_id, currency=currency)
                    for item in cast(list[dict[str, Any]], page_raw["movements"])
                ),
            )
        )
    return tuple(pages)


def _local(raw: dict[str, Any]) -> LocalMovement:
    return LocalMovement(
        local_id=str(raw["local_id"]),
        movement_group=str(raw["movement_group"]),
        kind=MovementKind(str(raw["kind"])),
        amount_ngwee=int(raw["amount_ngwee"]),
        provider_transaction_id=cast(str | None, raw.get("provider_transaction_id")),
        merchant_reference=cast(str | None, raw.get("merchant_reference")),
        provider_reference=cast(str | None, raw.get("provider_reference")),
        payment_id=cast(str | None, raw.get("payment_id")),
        payout_id=cast(str | None, raw.get("payout_id")),
        refund_id=cast(str | None, raw.get("refund_id")),
        checkout_id=cast(str | None, raw.get("checkout_id")),
        order_id=cast(str | None, raw.get("order_id")),
        job_id=cast(str | None, raw.get("job_id")),
        obligation_id=cast(str | None, raw.get("obligation_id")),
        collection_exception_id=cast(str | None, raw.get("collection_exception_id")),
        ledger_transaction_id=cast(str | None, raw.get("ledger_transaction_id")),
        ledger_linkage_id=cast(str | None, raw.get("ledger_linkage_id")),
        allocation_id=cast(str | None, raw.get("allocation_id")),
        actor_id=cast(str | None, raw.get("actor_id")),
        rail=cast(str | None, raw.get("rail")),
        leg=cast(str | None, raw.get("leg")),
    )


def _provider_collection(payload: dict[str, Any]) -> tuple[ProviderMovement, ...]:
    collected = collect_provider_pages(
        _pages(payload),
        configured_account_id=str(payload["configured_account_id"]),
        currency=str(payload["currency"]),
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )
    assert collected.complete
    return collected.movements


def test_configured_account_is_selected_instead_of_first_account() -> None:
    payload = _fixture()
    accounts = tuple(
        AccountSnapshot(
            account_id=str(row["account_id"]),
            currency=str(row["currency"]),
            available_balance_ngwee=int(row["available_balance_ngwee"]),
            ledger_balance_ngwee=int(row["ledger_balance_ngwee"]),
        )
        for row in cast(list[dict[str, Any]], payload["accounts"])
    )

    selected = select_configured_account(
        accounts,
        configured_account_id="acct-configured",
        currency="ZMW",
    )

    assert selected.account_id == "acct-configured"
    assert selected.account_id != accounts[0].account_id


@pytest.mark.parametrize(
    ("account_id", "currency", "message"),
    [
        ("acct-missing", "ZMW", "matched 0 rows"),
        ("acct-configured", "USD", "currency mismatch"),
    ],
)
def test_configured_account_mismatch_fails_closed(
    account_id: str,
    currency: str,
    message: str,
) -> None:
    account = AccountSnapshot("acct-configured", "ZMW", 1, 1)
    with pytest.raises(ValueError, match=message):
        select_configured_account((account,), configured_account_id=account_id, currency=currency)


def test_complete_pages_dedupe_identical_ids_and_retain_late_and_unparsed() -> None:
    payload = _fixture()

    result = collect_provider_pages(
        _pages(payload),
        configured_account_id="acct-configured",
        currency="ZMW",
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert result.complete
    assert result.stop_reason == "complete"
    assert result.observed_page_numbers == (1, 2, 3)
    assert result.duplicate_ids == ("txn-product",)
    assert tuple(row.movement_id for row in result.late_movements) == ("txn-after-cutoff",)
    assert any(row.movement_id == "txn-unparsed" for row in result.movements)


def test_omitted_page_is_incomplete() -> None:
    payload = _fixture()
    pages = _pages(payload)

    result = collect_provider_pages(
        (pages[0], pages[2]),
        configured_account_id="acct-configured",
        currency="ZMW",
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert not result.complete
    assert any("missing, repeated, or out of order" in issue for issue in result.issues)
    assert any("cursor chain mismatch" in issue for issue in result.issues)


def test_repeated_cursor_and_partial_failure_are_incomplete() -> None:
    payload = _fixture()
    pages = list(_pages(payload))
    pages[2] = replace(pages[2], cursor="cursor-2", error="provider timeout")

    result = collect_provider_pages(
        pages,
        configured_account_id="acct-configured",
        currency="ZMW",
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert any("cursor repeated" in issue for issue in result.issues)
    assert any("provider timeout" in issue for issue in result.issues)


def test_conflicting_duplicate_provider_id_is_not_deduped() -> None:
    payload = _fixture()
    pages = list(_pages(payload))
    duplicate = pages[1].movements[0]
    pages[1] = replace(
        pages[1], movements=(replace(duplicate, amount_ngwee=99999), *pages[1].movements[1:])
    )

    result = collect_provider_pages(
        pages,
        configured_account_id="acct-configured",
        currency="ZMW",
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert any("conflicting duplicate" in issue for issue in result.issues)


def test_late_provider_rows_are_deduped_by_stable_identity_too() -> None:
    payload = _fixture()
    pages = list(_pages(payload))
    late = pages[-1].movements[-1]
    pages[-1] = replace(
        pages[-1],
        movements=pages[-1].movements + (late,),
        total=pages[-1].total + 1 if pages[-1].total is not None else None,
    )
    pages[0] = replace(
        pages[0],
        total=pages[0].total + 1 if pages[0].total is not None else None,
    )
    pages[1] = replace(
        pages[1],
        total=pages[1].total + 1 if pages[1].total is not None else None,
    )

    result = collect_provider_pages(
        pages,
        configured_account_id=str(payload["configured_account_id"]),
        currency=str(payload["currency"]),
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert result.complete
    assert len(result.late_movements) == 1
    assert late.movement_id in result.duplicate_ids


def test_wrong_account_and_currency_are_explicit_page_issues() -> None:
    payload = _fixture()
    pages = list(_pages(payload))
    wrong = replace(pages[0].movements[0], account_id="acct-shared", currency="USD")
    pages[0] = replace(pages[0], movements=(wrong, *pages[0].movements[1:]))

    result = collect_provider_pages(
        pages,
        configured_account_id="acct-configured",
        currency="ZMW",
        cutoff_utc=_dt(payload["cutoff_utc"]),
    )

    assert any("not configured account" in issue for issue in result.issues)
    assert any("does not match 'ZMW'" in issue for issue in result.issues)


def test_matcher_aggregates_allocations_and_preserves_distinct_repeated_references() -> None:
    payload = _fixture()
    provider = _provider_collection(payload)
    local_rows = [_local(row) for row in cast(list[dict[str, Any]], payload["local_movements"])]
    local_rows.append(
        LocalMovement(
            local_id="unparsed-local",
            movement_group="unparsed-provider-movement",
            kind=MovementKind.UNKNOWN,
            amount_ngwee=2000,
            provider_transaction_id="txn-unparsed",
            ledger_transaction_id="ledger-unparsed",
        )
    )

    aggregates = aggregate_local_movements(local_rows)
    product = next(row for row in aggregates if row.movement_group == "collection-product")
    report = match_movements(provider, local_rows)

    assert product.amount_ngwee == 100000
    assert product.allocation_ids == ("allocation-a", "allocation-b")
    assert len(report.matches) == 9
    assert report.exact
    repeated = {
        match.provider_movement_id: match.local_movement_group
        for match in report.matches
        if match.provider_movement_id.startswith("txn-repeat")
    }
    assert repeated == {
        "txn-repeat-a": "collection-repeat-a",
        "txn-repeat-b": "collection-repeat-b",
    }


def test_unparsed_provider_movement_is_reported_not_dropped() -> None:
    payload = _fixture()
    provider = _provider_collection(payload)
    local_rows = tuple(
        _local(row) for row in cast(list[dict[str, Any]], payload["local_movements"])
    )

    report = match_movements(provider, local_rows)

    assert len(report.provider_unmatched) == 1
    assert report.provider_unmatched[0].identity == "txn-unparsed"
    assert "no mapped reference" in report.provider_unmatched[0].reason
    assert not report.exact


def test_incorrect_or_missing_ledger_linkage_fails_before_matching() -> None:
    payload = _fixture()
    raw = next(
        row
        for row in cast(list[dict[str, Any]], payload["local_movements"])
        if row["movement_group"] == "payout-refund"
    )

    with pytest.raises(ValueError, match="incorrect ledger linkage"):
        _local({**raw, "ledger_linkage_id": "order-unrelated"})
    with pytest.raises(ValueError, match="no ledger linkage evidence"):
        _local({**raw, "ledger_linkage_id": None})


def test_repeated_merchant_reference_without_stable_ids_is_ambiguous() -> None:
    payload = _fixture()
    provider = _provider_collection(payload)
    local_rows = [_local(row) for row in cast(list[dict[str, Any]], payload["local_movements"])]
    local_rows = [
        replace(
            row,
            provider_transaction_id=None,
            provider_reference=None,
        )
        if row.movement_group in {"collection-repeat-a", "collection-repeat-b"}
        else row
        for row in local_rows
    ]

    report = match_movements(provider, local_rows)

    reasons = [issue.reason for issue in report.ambiguous]
    assert reasons.count("merchant reference maps multiple distinct movements") == 2


def _bridge(payload: dict[str, Any], *, basis: CreditBasis | None = None) -> BalanceBridgeInput:
    raw = cast(dict[str, Any], payload["balance_bridge"])
    fees = tuple(
        FeeEvidence(
            fee_id=str(row["fee_id"]),
            source_movement_id=str(row["source_movement_id"]),
            amount_ngwee=cast(int | None, row.get("amount_ngwee")),
            reversed_ngwee=int(row["reversed_ngwee"]),
            previously_recovered_ngwee=int(row["previously_recovered_ngwee"]),
            recoverability_evidence_id=cast(str | None, row.get("recoverability_evidence_id")),
        )
        for row in cast(list[dict[str, Any]], raw["fees"])
    )
    return BalanceBridgeInput(
        account_id=str(raw["account_id"]),
        currency=str(raw["currency"]),
        statement_id=str(raw["statement_id"]),
        statement_source_hash=str(raw["statement_source_hash"]),
        statement_cutoff_utc=_dt(raw["statement_cutoff_utc"]),
        opening_funds_ngwee=int(raw["opening_funds_ngwee"]),
        settled_credits_ngwee=int(raw["settled_credits_ngwee"]),
        successful_outgoing_transfers_ngwee=int(raw["successful_outgoing_transfers_ngwee"]),
        successful_refunds_ngwee=int(raw["successful_refunds_ngwee"]),
        evidenced_reversals_ngwee=int(raw["evidenced_reversals_ngwee"]),
        unsettled_credits_ngwee=int(raw["unsettled_credits_ngwee"]),
        disputed_positions_ngwee=int(raw["disputed_positions_ngwee"]),
        observed_ledger_balance_ngwee=int(raw["observed_ledger_balance_ngwee"]),
        observed_available_balance_ngwee=int(raw["observed_available_balance_ngwee"]),
        credit_basis=basis or CreditBasis(str(raw["credit_basis"])),
        fees=fees,
    )


def test_gross_balance_bridge_is_exact_and_exposes_unsettled_and_disputed_positions() -> None:
    result = build_balance_bridge(
        _bridge(_fixture()),
        configured_account_id="acct-configured",
        currency="ZMW",
    )

    assert result.statement_id == "statement-2026-09-28"
    assert result.fees_subtracted_ngwee == 4000
    assert result.unsettled_credits_ngwee == 7000
    assert result.disputed_positions_ngwee == 9000
    assert result.expected_ledger_balance_ngwee == 249000
    assert result.expected_available_balance_ngwee == 240000
    assert result.exact


def test_net_credit_does_not_double_count_the_fee() -> None:
    value = _bridge(_fixture(), basis=CreditBasis.NET_OF_FEES)
    value = replace(value, settled_credits_ngwee=201000)

    result = build_balance_bridge(
        value,
        configured_account_id="acct-configured",
        currency="ZMW",
    )

    assert result.fees_subtracted_ngwee == 0
    assert result.expected_ledger_balance_ngwee == 249000
    assert result.exact


def test_missing_fee_evidence_is_unresolved_not_zero() -> None:
    value = _bridge(_fixture())
    value = replace(value, fees=(replace(value.fees[0], amount_ngwee=None),))

    result = build_balance_bridge(
        value,
        configured_account_id="acct-configured",
        currency="ZMW",
    )

    assert result.fees_subtracted_ngwee == 0
    assert result.unresolved == ("fee 'fee-collection' has no amount evidence",)
    assert not result.exact


def test_evidenced_fee_reversal_changes_the_bridge_instead_of_deleting_history() -> None:
    value = _bridge(_fixture())
    without_reversal = replace(value, fees=(replace(value.fees[0], reversed_ngwee=0),))

    result = build_balance_bridge(
        without_reversal,
        configured_account_id="acct-configured",
        currency="ZMW",
    )

    assert result.fees_subtracted_ngwee == 5000
    assert result.ledger_difference_ngwee == 1000
    assert not result.exact


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            replace(_bridge(_fixture()), account_id="acct-wrong"),
            "statement account mismatch",
        ),
        (replace(_bridge(_fixture()), currency="USD"), "statement currency mismatch"),
        (
            replace(_bridge(_fixture()), statement_source_hash=""),
            "source hash are required",
        ),
        (
            replace(
                _bridge(_fixture()),
                statement_cutoff_utc=datetime.fromisoformat("2026-09-29T01:59:59+02:00"),
            ),
            "must use UTC",
        ),
    ],
)
def test_balance_bridge_rejects_unbound_provider_statement(
    value: BalanceBridgeInput,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_balance_bridge(
            value,
            configured_account_id="acct-configured",
            currency="ZMW",
        )


@pytest.mark.parametrize(
    ("refundable", "cost", "expected_deduction", "expected_refund"),
    [
        (100000, 3000, 3000, 97000),
        (10000, 1300, 500, 9500),
        (100000, 0, 0, 100000),
    ],
)
def test_q5_proposal_uses_actual_cost_bounded_by_integer_ngwee_ceiling(
    refundable: int,
    cost: int,
    expected_deduction: int,
    expected_refund: int,
) -> None:
    result = calculate_proposed_cost_evidence(
        refundable_paid_ngwee=refundable,
        actual_attributable_cost_ngwee=cost,
        policy_eligible=True,
    )

    assert result.proposed_deduction_ngwee == expected_deduction
    assert result.proposed_refund_ngwee == expected_refund
    assert not result.enabled


def test_q5_unknown_cost_stays_unresolved_and_mandatory_zero_stays_zero() -> None:
    unknown = calculate_proposed_cost_evidence(
        refundable_paid_ngwee=100000,
        actual_attributable_cost_ngwee=None,
        policy_eligible=True,
    )
    mandatory_zero = calculate_proposed_cost_evidence(
        refundable_paid_ngwee=100000,
        actual_attributable_cost_ngwee=5000,
        policy_eligible=True,
        mandatory_zero_reason="seller failure",
    )

    assert unknown.proposed_deduction_ngwee is None
    assert unknown.unresolved
    assert mandatory_zero.proposed_deduction_ngwee == 0
    assert mandatory_zero.proposed_refund_ngwee == 100000


def test_q5_rejects_negative_provider_cost_evidence() -> None:
    with pytest.raises(ValueError, match="non-negative integer ngwee"):
        calculate_proposed_cost_evidence(
            refundable_paid_ngwee=100000,
            actual_attributable_cost_ngwee=-1,
            policy_eligible=True,
        )


def test_q6_exposes_required_inputs_without_treating_account_cash_as_entitlement() -> None:
    evidence = PayoutDecisionEvidence(
        obligation_id="obligation-1",
        account_id="acct-configured",
        currency="ZMW",
        snapshot_at=datetime.fromisoformat("2026-09-28T23:59:59+00:00"),
        released_liability_ngwee=10000,
        available_balance_ngwee=200000,
        active_holds_ngwee=None,
        kyc_evidence_id=None,
        immutable_destination_fingerprint="destination-hash",
        dispatch_claim_id=None,
        provider_settlement_evidence_id="settlement-1",
        order_release_evidence_id=None,
    )

    gaps = payout_decision_evidence_gaps(evidence)

    assert "active holds are unresolved" in gaps
    assert "KYC evidence missing" in gaps
    assert "dispatch claim missing" in gaps
    assert "order release missing" in gaps
    assert "configured account availability is below this obligation" not in gaps


def _synthetic_acceptance_rows(payload: dict[str, Any]) -> tuple[AcceptanceEvidenceRow, ...]:
    rows: list[AcceptanceEvidenceRow] = []
    for raw in cast(list[dict[str, Any]], payload["acceptance_rows"]):
        rows.append(
            AcceptanceEvidenceRow(
                case_id=int(raw["case_id"]),
                verdict=EvidenceVerdict(str(raw["verdict"])),
                origin=EvidenceOrigin(str(raw["origin"])),
                candidate_sha="synthetic-candidate",
                deployment_id="synthetic-deployment",
                schema_id="synthetic-schema",
                observed_at=datetime.fromisoformat("2026-09-28T23:59:59+00:00"),
                simulated=bool(raw["simulated"]),
            )
        )
    return tuple(rows)


def test_exact_24_row_synthetic_fixture_cannot_be_called_provider_acceptance() -> None:
    result = assess_acceptance_evidence(_synthetic_acceptance_rows(_fixture()))

    assert result.expected_count == 24
    assert result.observed_count == 24
    assert result.passed_count == 0
    assert not result.certifiable
    assert all("NOT_RUN" in issue for issue in result.issues)


def test_evidence_parser_retains_synthetic_not_run_rows_without_inventing_identity() -> None:
    payload = _fixture()
    raw_rows = cast(list[dict[str, Any]], payload["acceptance_rows"])
    for raw in raw_rows:
        raw.update(
            {
                "candidate_sha": "synthetic-candidate",
                "deployment_id": "synthetic-deployment",
                "schema_id": "synthetic-schema",
                "observed_at": "2026-09-28T23:59:59+00:00",
            }
        )

    rows = parse_acceptance_evidence_rows(payload)
    assessment = assess_acceptance_evidence(rows)

    assert len(rows) == 24
    assert rows[0].merchant_reference is None
    assert not assessment.certifiable
    assert assessment.passed_count == 0


def test_evidence_parser_rejects_non_identity_ledger_values() -> None:
    payload = _fixture()
    first = cast(list[dict[str, Any]], payload["acceptance_rows"])[0]
    first.update(
        {
            "observed_at": "2026-09-28T23:59:59+00:00",
            "ledger_transaction_ids": [""],
        }
    )

    with pytest.raises(ValueError, match="nonempty strings"):
        parse_acceptance_evidence_rows(payload)


def test_missing_duplicate_and_missing_identity_rows_fail_independently() -> None:
    rows = list(_synthetic_acceptance_rows(_fixture()))
    case_12 = replace(
        rows[11],
        verdict=EvidenceVerdict.PASS,
        origin=EvidenceOrigin.STAGING_PROVIDER,
        simulated=False,
        actor_id="buyer",
        rail="airtel",
        merchant_reference="ord-service-balance",
        provider_reference="lenco-service-balance",
        receipt_id="receipt-balance",
        job_id="job-1",
        obligation_id="obligation-balance",
        ledger_transaction_ids=("ledger-balance",),
    )
    rows[11] = case_12
    rows.pop(0)
    rows.append(rows[-1])

    result = assess_acceptance_evidence(rows)

    assert any("duplicate acceptance case 24" in issue for issue in result.issues)
    assert any("missing acceptance cases [1]" in issue for issue in result.issues)
    assert any("case 12 missing required evidence ['leg']" in issue for issue in result.issues)
    assert not result.certifiable
