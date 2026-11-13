# Event ticket money: hold, advance and recovery policy

Founder policy (2026-11-13). Code: `services/api/app/services/escrow/event_release.py`,
`services/api/app/services/events/advance_policy.py`. Schema: migration
`20261113174500_event_ticket_integrity.sql`.

## Who gets money when

| Organiser            | Before the event                                                                                                                        | After the event                        |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Unverified (default) | Nothing. 100% held.                                                                                                                     | Full release 24 h after the event ends |
| Verified             | Up to `event_verified_organiser_advance_bps` (default 5000 = 50%) of each order bought more than 14 days ahead, 7 days before the event | Remainder 1 day after the event ends   |

Verified means all of: vendor `active`; an **approved** KYC record at tier
`event_advance_min_kyc_tier` or higher (default 2); the advance undertaking accepted at
the current terms version (`POST /organiser/advance/undertaking`); no open advance debt;
never blacklisted. Any lookup failure means no advance.

No release is ever made for an event that is cancelled, unpublished (draft / moderation
hold) or whose order escrow is not funded.

## Config (`platform_config`, integers)

| Key                                    | Default | Meaning                                                                                  |
| -------------------------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `event_verified_organiser_advance_bps` | 5000    | Advance share for verified organisers, capped at 5000. 0 turns advances off for everyone |
| `event_advance_min_kyc_tier`           | 2       | Minimum approved KYC tier                                                                |
| `event_advance_repayment_days`         | 14      | Days to repay a recovered advance                                                        |

## If an event with an advance is cancelled

1. The release sweep (and the refund job, before it pays) posts `event_advance_recovery`:
   the organiser's advance becomes an `organiser_receivable` and the platform hands back
   its captured commission and fee. The order's escrow again holds the full ticket price.
2. The organiser-cancel refund job refunds the buyer in full from escrow (platform funds).
   While payouts are switched off the job stays queued.
3. An `organiser_advance_debts` row records the debt (due after the repayment window).
4. The receivable is netted automatically against any money the platform owes the
   organiser (`organiser_receivable_offset`). Cash repayments confirmed by finance are
   posted with `record_organiser_repayment` (`organiser_receivable_repaid`).
5. `POST /internal/event-advance-debts/tick` (cron, `INTERNAL_EVENT_ADVANCE_DEBTS_TOKEN`)
   suspends organisers with an overdue debt, blacklists the debt (no future advances) and
   flags it for legal follow-up. Every step writes `audit_log`.

Every entry is a balanced ledger transaction.

## Later option: protection fee (not built)

A small per-ticket "event protection" fee credited to a platform reserve account would
fund refunds when an organiser never repays, instead of the loss falling on platform
cash. This needs a reserve ledger account, a buyer-facing fee line and legal review.
