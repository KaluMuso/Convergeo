"""Clawback netting — recover post-release refunds from vendor payouts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClawbackNettingStep:
    """One payout netting step against outstanding clawback."""

    gross_payout_ngwee: int
    clawback_outstanding_before_ngwee: int
    clawback_applied_ngwee: int
    net_payout_ngwee: int
    clawback_outstanding_after_ngwee: int


def clawback_outstanding_from_payable_balance(vendor_payable_balance_ngwee: int) -> int:
    """Positive vendor_payable balance = vendor owes platform (clawback outstanding)."""
    return max(0, vendor_payable_balance_ngwee)


def net_clawback_from_payout(
    *,
    gross_payout_ngwee: int,
    clawback_outstanding_ngwee: int,
) -> ClawbackNettingStep:
    """Apply clawback netting to a single payout without over-clawing."""
    gross = max(0, gross_payout_ngwee)
    outstanding = max(0, clawback_outstanding_ngwee)
    applied = min(gross, outstanding)
    net = gross - applied
    remaining = outstanding - applied
    return ClawbackNettingStep(
        gross_payout_ngwee=gross,
        clawback_outstanding_before_ngwee=outstanding,
        clawback_applied_ngwee=applied,
        net_payout_ngwee=net,
        clawback_outstanding_after_ngwee=remaining,
    )


def net_clawback_across_payouts(
    *,
    payout_amounts_ngwee: tuple[int, ...],
    initial_clawback_outstanding_ngwee: int,
) -> tuple[ClawbackNettingStep, ...]:
    """Net clawback across multiple sequential payouts until cleared."""
    steps: list[ClawbackNettingStep] = []
    outstanding = max(0, initial_clawback_outstanding_ngwee)
    for gross in payout_amounts_ngwee:
        step = net_clawback_from_payout(
            gross_payout_ngwee=gross,
            clawback_outstanding_ngwee=outstanding,
        )
        steps.append(step)
        outstanding = step.clawback_outstanding_after_ngwee
        if outstanding == 0:
            break
    return tuple(steps)
