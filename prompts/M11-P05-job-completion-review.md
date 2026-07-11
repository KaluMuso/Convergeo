> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (it shares `refs/stash` across sibling worktrees and corrupts parallel agents — to check a pre-existing-master failure, `git worktree add /tmp/base origin/master` and compare, never stash). **⚙ CI GATING:** your `test_job_completion.py` DB tests must be isolation-clean; converger wires them into the rls blocking step. **Run the FULL `uv run pytest` before reporting.**

# M11-P05 — Completion, confirmation & review

## 1. Context

**Grounded against as-built `master` (M11-P04 MERGED):**

- **Money spine from M11-P04** (`services/api/app/services/rfq/engagement.py`, merged): one order per accepted job; `accept_quote(...)` created the `service_deposit` leg; **`create_balance_item(order_id)`** adds the `service_balance` item (= total − deposit) on the SAME order; commission is 12% of total, snapshotted, **captured once at release** (never on the balance leg). **Reuse `create_balance_item`; do NOT re-capture commission or re-snapshot.**
- **Order confirm pattern (M09-P06/M09-P10, merged):** delivered/confirmed → auto-confirm after a config window → escrow release via `release-{order_id}` (single idempotency key). Mirror this for job completion: provider marks complete → customer confirms (or 48h auto-confirm, config) → balance settlement + release **exactly once** via the same `release-{order_id}` key (never a second key).
- **Review write API (M15-P01, merged):** verified-purchase reviews only. Gate the job review on a **completed** job (verified-engagement).
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P05.

## 2. Objective & scope

Job completion flow: provider marks complete → customer confirms (48h auto-confirm fallback, config) → balance payment settles + escrow releases once → review unlocked (post-completion only, feeds vendor rating).
**Non-goals:** no commission re-capture (M11-P04 owns the single-capture), no new payment method (reuse M08), no review-aggregate change (M15-P02).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/job_completion.py` (provider mark-complete / customer confirm / auto-confirm tick or reuse the existing order-jobs tick pattern) · `apps/customer/app/[locale]/account/jobs/[id]/_components/complete-confirm.tsx` · `apps/vendor/app/[locale]/jobs/[id]/page.tsx` (provider mark-complete UI) · `services/api/tests/test_job_completion.py`
  **Guardrail: nothing else. Do NOT edit `engagement.py`/`release.py`/`commissions/*`/`main.py`, db.ts, other job routers. No migration (state derives from order/job status + events).**

## 4. Implementation spec

- **`job_completion.py`** (auth, owner/provider-scoped, uniform envelope, rate-limited): `POST /jobs/{id}/complete` (provider marks complete — records a completion event); `POST /jobs/{id}/confirm` (customer confirms → `create_balance_item` + settle balance via M08 checkout + release via `release-{order_id}`, **once**); auto-confirm after `job_autoconfirm_hours` (config, default 48) mirroring the merged order auto-confirm job. Double-confirm → idempotent no-op. Release exactly once (reuse the order engine's `release-{order_id}` idempotency — never double-release).
- **UI:** provider mark-complete (vendor jobs page); customer complete-confirm (balance amount `formatK`, confirm CTA); 360px; i18n via the existing `services`/`vendor` namespaces (append-rule if a new key is needed, but prefer existing keys — do NOT touch `services.json` if avoidable, and NEVER `vendor.json`/`marketing.json` this wave).

## 5–9. Security etc.

Provider-scoped mark-complete; customer-scoped confirm; balance release **exactly once** (single `release-{order_id}` key — assert no double-release in a test); auto-confirm window honored; review gated on completed job; no float; no secrets.

## 10. Tests (RUN before reporting)

`test_job_completion.py`: **double-confirm idempotency** (second confirm → no second release/balance); **auto-confirm** job honors the window (before → held, after → released once); **review gating** (review rejected pre-completion, accepted post); balance leg created once. `pnpm --filter customer build`, `pnpm --filter vendor build`, `pnpm typecheck/lint/test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Balance release follows confirm exactly once; auto-confirm honors the window; review only post-completion.
- [ ] No commission re-capture (M11-P04 single-capture reused); no migration; customer+vendor builds + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P05 — Completion, confirmation & review
**STATUS/FILES/DEVIATIONS** (how confirm settles the balance + releases once via `release-{order_id}`; auto-confirm window; review gate) **/TESTS** (paste double-confirm + auto-confirm + review-gating + full-pytest tail) **/EXCERPTS** the confirm→balance→single-release path — nothing else **/QUESTIONS**
