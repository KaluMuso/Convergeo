"""Ticket platform-fee incidence (strategy §3.3).

The platform cut is a fixed 5% (500 bps) of the ticket line. Organisers choose
who pays it:

* ``organiser`` (default, absorb) — buyer pays the ticket price; commission is
  captured from organiser settlement as today.
* ``buyer`` (pass-through) — buyer pays ticket + 5%; organiser settlement keeps
  the full ticket line (commission rate 0) and the extra is recorded as a
  platform fee, never released to the organiser.

Money movement of the fee is not a new payout type. Event escrow still releases
``sum(qty * unit_price)`` minus any absorb-fee commission.
"""

from __future__ import annotations

from typing import Literal

EVENT_TICKETS_RATE_BPS = 500
FREE_EVENTS_RATE_BPS = 0

FeePayer = Literal["organiser", "buyer"]


def normalize_fee_payer(value: object) -> FeePayer:
    return "buyer" if value == "buyer" else "organiser"


def platform_fee_ngwee(*, line_total_ngwee: int, fee_payer: FeePayer, is_free: bool) -> int:
    if is_free or line_total_ngwee <= 0 or fee_payer != "buyer":
        return 0
    return (line_total_ngwee * EVENT_TICKETS_RATE_BPS) // 10_000


def commission_rate_bps(*, fee_payer: FeePayer, is_free: bool) -> int:
    if is_free:
        return FREE_EVENTS_RATE_BPS
    if fee_payer == "buyer":
        return 0
    return EVENT_TICKETS_RATE_BPS


def checkout_total_ngwee(*, subtotal_ngwee: int, platform_fee: int) -> int:
    return subtotal_ngwee + platform_fee
