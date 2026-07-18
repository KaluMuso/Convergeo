> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** Foreground blocking only; run the FULL `uv run pytest` before reporting. **MONEY-CRITICAL** — integer ngwee only, float on money is a review-blocking bug.

# M08-P08b — Capture commission at escrow release (prepaid enablement prerequisite)

## Why this exists (context)

PR #274 (`services/api/app/services/payments/settlement.py`) made a successful prepaid Lenco collection post `CHARGE_RECEIVED` → **debit `platform_cash +gross`, credit `escrow −gross`**, so **escrow now holds the full gross** for every prepaid order at collection time. But the two vendor-release sites post **only** `RELEASE_TO_VENDOR(net)` and never post `COMMISSION_CAPTURE`:

- `services/api/app/services/escrow/release.py` → `_post_release` (product orders).
- `services/api/app/routers/job_completion.py` → `_release_service_order` (service orders).

`capture_order_commission` is wired only into `services/api/app/services/payments/cod.py:405`. Net effect: `escrow` retains `(gross − net) = commission` **forever** and `commission_revenue` is **never credited** for prepaid product or service orders. This also contradicts the documented invariant in `services/api/app/services/rfq/engagement.py` ("the merged escrow-release / COD paths capture commission EXACTLY ONCE for the whole order — never on the deposit leg"), which was never implemented on the escrow-release side.

**This is the gating prerequisite before prepaid (MoMo/card) may be enabled.** Until it lands, enabling prepaid strands commission in escrow on every prepaid order and under-recognizes platform revenue; the daily reconciliation and vendor-payable math drift permanently.

## Target accounting (per order, whole lifecycle)

| Event | Template | platform_cash | escrow | commission_revenue | vendor_payable |
|-------|----------|--------------:|-------:|-------------------:|---------------:|
| collection success (PR #274) | `CHARGE_RECEIVED` | +gross | −gross | | |
| **release (ADD)** | `COMMISSION_CAPTURE` | | **+commission** | **−commission** | |
| release (existing) | `RELEASE_TO_VENDOR` | | +net | | −net |
| **escrow net** | | | **0** | | |

`commission + net = gross` (both derive from `compute_order_commission(commission_snapshot)`), so escrow zeroes **exactly**. Zero-commission orders (free events / 0%): no capture leg, release posts full gross, escrow still → 0.

## Required fix

Post `COMMISSION_CAPTURE` **before** `RELEASE_TO_VENDOR` at **both** release sites, from the order's purchase-time `commission_snapshot`, keyed for exactly-once capture. Mirror the COD pattern in `cod.py:confirm_cod_collection` (capture → release).

**Part 1 — `escrow/release.py` (products).** In `evaluate_and_release`, when `outcome == "released"`, immediately **before** `_post_release(...)`:
- Call `capture_order_commission(order_id=order_id, commission_snapshot=context.commission_snapshot, idempotency_key_prefix=f"release-{order_id}")`.
- Keep the existing `net_ngwee = compute_net_ngwee(...)` and `_post_release(...)` unchanged (still releases `net`).

**Part 2 — `job_completion.py` (services).** In `confirm_job_completion`, insert the same capture call **after** `_settle_balance(...)` and **before** `_release_service_order(...)` — so both the deposit charge (from collection success) and the balance charge (`_settle_balance`) are in escrow before commission is captured. Preserves the existing "release before complete" ordering (finding #7).

## Ordering & idempotency (the correctness spine — do not deviate)

- **Capture before release.** A partial failure must never release `net` without capturing commission. Both posts are idempotent, so a re-run (release sweeper overlap, double-confirm, auto-confirm tick) re-drives to the same single capture + single release.
- **Idempotency keys:** capture uses prefix `release-{order_id}` → `capture_order_commission` posts per-line `release-{order_id}-commission-{listing_id|index}`. The release stays keyed `release-{order_id}` (`release_idempotency_key`). These are distinct strings (`release-{oid}` vs `release-{oid}-commission-…`) and distinct from COD's `cod-commission-{order_id}` — no collision, no double capture across paths.
- The product `already_released` gate and the service `status == completed` idempotent no-op remain the outer guards; the commission idempotency key is the inner belt-and-suspenders.

## Files (ONLY)

- Modify `services/api/app/services/escrow/release.py` (import + call `capture_order_commission` in `evaluate_and_release`; optionally add `commission_ngwee` to `ReleaseResult` for observability).
- Modify `services/api/app/routers/job_completion.py` (import + call `capture_order_commission` between settle-balance and release).
- Add/extend `services/api/tests/test_release.py` and `services/api/tests/test_service_escrow.py` (or a focused new `services/api/tests/test_release_commission.py`).
- **Do NOT touch:** `settlement.py`, `state.py`, `webhook_verify.py` (PR #274 owns them), `cod.py`, `commissions/engine.py`, refund templates/paths, `ledger/templates.py`, any migration, any env / n8n / gate / config.

## Constraints — do NOT

- No migration, no env change, no n8n, no deployment, no payment-enablement / kill-switch change.
- Do not change `RELEASE_TO_VENDOR` net math, `compute_net_ngwee`, or the release idempotency key.
- Do not re-capture at the deposit or balance leg (`rfq/engagement.py` invariant: single capture at release).
- Do not touch COD (`cod.py`) or refunds — they are already correct / out of scope.

## Acceptance criteria

1. Product and service release each post exactly one `COMMISSION_CAPTURE` set **before** `RELEASE_TO_VENDOR`; the `escrow` account nets to **0** across `charge → capture → release` for the order.
2. `Σ per-line captured commission == gross − net` (integer-exact, same snapshot, same floor math).
3. Idempotent: repeated `evaluate_and_release` / double `confirm_job_completion` → one capture set, one release; balances stable.
4. Zero-commission order (free events / 0%) → no capture leg; release posts full gross; escrow → 0.
5. COD path unchanged (still `cod-commission-*` only; no `release-*-commission-*` row); refunds unchanged.
6. `commission_revenue` is credited exactly `commission` for the order; `vendor_payable −net`; `platform_cash` unchanged at release.

## Tests (RUN) — DB-backed ledger harness + fakes; **no live/sandbox provider calls**

Use the existing `tests/test_ledger.py` DB harness (`db` / `PgConn`, seeded account IDs) and fake service clients, in the style of `tests/test_prepaid_settlement.py`.

- **Product lifecycle zeroes escrow:** seed order + a `CHARGE_RECEIVED` for gross; run `evaluate_and_release`; assert `COMMISSION_CAPTURE` + `RELEASE_TO_VENDOR` posted, `commission_revenue` credited `commission`, and the escrow account balance = 0.
- **Idempotent release overlap:** call `evaluate_and_release` twice → one commission set, one release, balances stable.
- **Zero-commission (free / 0%):** no capture leg; release = gross; escrow → 0.
- **Capture-before-release atomicity:** patch `_post_release` to raise → commission captured, order **not** `already_released`; re-run completes with no double capture.
- **Service path (`job_completion`):** confirm → balance `CHARGE_RECEIVED` + commission capture + release; escrow → 0; double-confirm idempotent (no second capture/release).
- **Cross-path:** a COD order still captures via `cod-commission-*` only (assert no `release-*-commission-*` transaction) → no double capture.

Then the **FULL** `uv run pytest` + `uv run ruff check` + `uv run mypy`.

## Report

STATUS / FILES / DEVIATIONS (insertion points at both sites; key prefixes; any `ReleaseResult` field added) / TESTS (paste the escrow-zeroes-out assertion for both product and service, the idempotent-overlap result, and the full-pytest tail) / EXCERPTS (the capture-before-release blocks in both files) / QUESTIONS.

---

**Enablement note (for the reviewer, not the implementer):** after this merges, the prepaid escrow lifecycle balances end-to-end (`escrow → 0`, commission recognized at release). Combined with PR #274 (charge at collection) this closes the durable-accounting prerequisite; prepaid payment enablement remains a separate, explicit decision.
