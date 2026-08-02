> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P20 — Launch proof: payment, scanner, OTP, automation, recovery, load, rollback `[OPS]` ⚠ money

## 1. Context
**Wave W7 — the last gate.** Runs after W1–W6 and **R02-P19**.

Standing state as of 2026-08-01: `payments`, `orders`, `ledger_transactions`, `ledger_postings`, `refunds`, `payouts`, `kyc_records` are **all 0 on both database projects**. Nothing has ever moved through the money engine outside tests. The drill tooling now exists (`scripts/drills/lenco_sandbox_money_drill.py` with Airtel sandbox support, `docs/ops/lenco/sandbox-money-drill.md`, `docs/production-readiness/2026-07-22/money-drill-runbook.md`), so the remaining blocker is **F9b credentials**, which the founder pursues in parallel.

**Payouts stay disabled until every leg below is complete.** Sandbox only. No production collections.

**Type:** `[OPS]` — founder executes privileged steps; the agent prepares runners and evidence templates and never holds credentials.

## 2. Objective & scope
The complete evidence pack that a go/no-go can actually be signed against.
**Non-goals:** enabling `public_launch`; enabling payouts; production money.

## 3. Files (edit ONLY these)
- `docs/production-readiness/<YYYY-MM-DD>/launch-proof/` (new — one file per leg)
- `docs/production-readiness/<YYYY-MM-DD>/go-no-go-report.md` (new, dated — **do not edit the 2026-07-20 one**; dated audits are annotated, never rewritten)

## 4. Implementation spec — one evidence file per leg

1. **Payment (S1–S6, sandbox).** MoMo push and card widget → `CHARGE_RECEIVED` + escrow hold; **ledger legs balance to zero**; webhook replayed → **single** transaction (23505 dedupe); `COMMISSION_CAPTURE` **before** `RELEASE_TO_VENDOR`; refund `rfd-*` lane 1 and lane 2; forced Lenco-vs-ledger mismatch raises an **actionable** alert. Redact refs.
2. **Scanner.** Dynamic-QR issue → scan → **first-scan-wins** under two concurrent scans; offline scan then sync (VF-P05's cache).
3. **OTP.** Phone OTP sign-in on a real device; rate limit; expiry; no OTP in logs.
4. **Automation.** Every activated n8n workflow ticks authenticated and idempotent; a money tick forced to fail produces an alert (**R02-P04**); no workflow runs unauthenticated.
5. **Recovery.** Restore a **real** dump to scratch; RTO/RPO recorded (R02-P04 evidence may be referenced, not re-used as a substitute).
6. **Load.** k6 checkout + browse at 100 concurrent; **p95 <500ms**; then the invariant check: **zero oversell, zero ledger imbalance, zero invoice-number gap**. The invariant check is the point — a fast system that loses money is not a passing system.
7. **Rollback.** Timed Vercel rollback and API image rollback, both executed, both timed.

Each file: what ran, when, by whom, the raw (redacted) output, and a verdict of `PASS` / `FAIL` / `BLOCKED_EXTERNAL` — never a bare assertion.

## 5. Security / conventions
Sandbox credentials only; never committed. Payouts disabled throughout. No production money. No customer PII in evidence. `public_launch` stays `false` until a separate, explicit founder decision.

## 10. Tests (RUN before reporting)
- `python scripts/drills/lenco_sandbox_money_drill.py` per the runbook.
- `python load/invariant-check.py` after the k6 run.
- `pnpm e2e` against the deployed target.
- `bash scripts/ops/verify_live.sh` — final G0–G9 matrix.

## 11. Acceptance criteria / DoD
- [ ] All seven legs have evidence files with explicit verdicts.
- [ ] Ledger balances; replay is idempotent; commission precedes release.
- [ ] First-scan-wins proven under concurrency.
- [ ] Load p95 <500ms **and** all three invariants clean.
- [ ] Rollback executed and timed on both planes.
- [ ] A dated go/no-go report with a signature block; payouts still disabled.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P20 — Launch proof
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste each leg's verdict line · **EXCERPTS:** the ledger balance proof · **QUESTIONS:** anything that must reach the founder before sign-off
