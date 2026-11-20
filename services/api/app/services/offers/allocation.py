"""Integer-ngwee allocation primitives for offers (W8). No floats anywhere.

``allocate_pro_rata`` spreads an amount across weighted lines with the
largest-remainder (Hamilton) method: every share is floor(amount * w / W), and
the ngwee left over go one each to the lines with the largest fractional
remainder, ties broken by line position. The shares always sum to exactly
``amount`` and, when ``amount <= sum(weights)``, no share exceeds its weight —
so a discount never makes a line negative.

``split_line_units`` turns an allocated line total into at most two
(qty, unit price) parts with integral unit prices that sum to the total, so
every downstream reader that computes ``qty * unit_price_ngwee`` (commission,
refunds, escrow, invoices) sees the discounted amount unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence


def allocate_pro_rata(amount: int, weights: Sequence[int]) -> list[int]:
    """Split ``amount`` ngwee across ``weights`` deterministically (sum exact)."""
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("amount must be int ngwee")
    if amount < 0:
        raise ValueError("amount must be non-negative")
    for weight in weights:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise TypeError("weights must be int ngwee")
        if weight < 0:
            raise ValueError("weights must be non-negative")
    if not weights:
        if amount:
            raise ValueError("cannot allocate a non-zero amount across no lines")
        return []
    total_weight = sum(weights)
    if total_weight == 0:
        if amount:
            raise ValueError("cannot allocate a non-zero amount across zero weights")
        return [0 for _ in weights]
    shares = [amount * weight // total_weight for weight in weights]
    remainders = [amount * weight % total_weight for weight in weights]
    leftover = amount - sum(shares)
    order = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in order[:leftover]:
        shares[index] += 1
    return shares


def split_line_units(line_total_ngwee: int, qty: int) -> list[tuple[int, int]]:
    """Return [(qty, unit_price)] parts summing to ``line_total_ngwee``.

    ``base = total // qty``; the ``total % qty`` remainder units cost one
    ngwee more. The cheaper part comes first. A part may have unit price 0 only
    when the caller passes a total below ``qty`` (callers reject that for
    paid lines).
    """
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise ValueError("qty must be a positive int")
    if isinstance(line_total_ngwee, bool) or not isinstance(line_total_ngwee, int):
        raise TypeError("line total must be int ngwee")
    if line_total_ngwee < 0:
        raise ValueError("line total must be non-negative")
    base, remainder = divmod(line_total_ngwee, qty)
    parts: list[tuple[int, int]] = []
    if qty - remainder > 0:
        parts.append((qty - remainder, base))
    if remainder > 0:
        parts.append((remainder, base + 1))
    return parts


def percent_of(amount_ngwee: int, percent: int) -> int:
    """floor(amount * percent / 100) — the discount, rounded in the vendor's favour."""
    if amount_ngwee < 0 or not 0 <= percent <= 100:
        raise ValueError("invalid amount or percent")
    return amount_ngwee * percent // 100
