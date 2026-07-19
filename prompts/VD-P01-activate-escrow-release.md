> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P01 — Activate escrow auto-release + order-jobs workflows `[OPS]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` DL-4 / §6; MR-W01; `release-gates.md` G5. **Depends on VB-P04** (release accounting proven) + VA-P03 (API pinned). **Live (2026-07-19, verified):** n8n has **only 2 active workflows** (notification-dispatch, payment-reconciliation). `release-job.json` and `order-jobs.json` are committed as `active:false` shells → their `/internal/*` routes exist (`internal_release_job.py`, `internal_order_jobs.py`) but **never fire**, so escrow can never auto-release.
**Type:** `[OPS]` — Cursor prepares the import notes + evidence doc + a token-check; the **founder** imports/activates in n8n (credentials + `X-Internal-Token`).

## 2. Objective & scope
Activate `release-job` (+ `order-jobs`) with correct tokens, fix the `order-jobs` fan-out ordering, and prove one authenticated, idempotent release tick on the sandbox stack.
**Non-goals:** ticket workflows (VD-P02); money-tick error alerting (VD-P06, runs **after** this on the same JSONs); production money enablement.

## 3. Files (create ONLY these / edit ONLY these)
- `infra/n8n/release-job.json`, `infra/n8n/order-jobs.json` (swap `REPLACE_WITH_CREDENTIAL_ID`; fix fan-out order only)
- `…/vision-audit/evidence/n8n-release.md`
**Guardrail: do NOT touch other `infra/n8n/*.json` (VD-P02/P03/P06 own those).**

## 4. Implementation spec
- **`order-jobs.json` fan-out fix:** the single hourly trigger currently wires `auto-confirm` **and** `auto-release` in parallel — n8n does not guarantee order. Chain them so **auto-confirm precedes auto-release** (confirm output → release input), so release never acts on an order the confirm pass hasn't transitioned. Bodies keep `{"limit":50}`.
- Import + set `active:true`; bind `INTERNAL_RELEASE_JOB_TOKEN` (release-job) and `INTERNAL_ORDER_JOBS_TOKEN` (order-jobs) via n8n Header-Auth credentials.
- Prove on sandbox: one authenticated tick returns 200; a due sandbox order releases exactly once; a re-tick does **not** double-release (idempotency is server-side in `escrow/release.py` — confirm it holds under overlap); an unauthenticated tick → 401.

## 9. Security
- Tokens live in n8n credentials / host env, never in the JSON or evidence doc. `X-Internal-Token` required (401 without). Do not log tokens.

## 10. Tests / verification (RUN before reporting)
- Authenticated tick → 200 with a release; execution id recorded.
- Re-run tick on the same order → no second `RELEASE_TO_VENDOR` leg (ledger unchanged).
- Unauthenticated POST to the internal route → 401.
- `order-jobs` confirms-before-releases proven (execution log shows ordering).

## 11. Acceptance criteria / DoD (maps to G5 / MR-W01)
- [ ] `release-job` + `order-jobs` active with correct tokens.
- [ ] Sandbox escrow releases exactly once; re-tick safe; unauth 401.
- [ ] `order-jobs` auto-confirm precedes auto-release.
- [ ] Execution ids recorded in `n8n-release.md`; no production money touched.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P01 — Activate escrow auto-release + order-jobs
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste tick responses + execution ids (redacted) + re-tick ledger diff
**EXCERPTS:** the `order-jobs` fan-out ordering change
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
