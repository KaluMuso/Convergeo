# Output 3 — Waves & Phases (Mountains → Pebbles → Waves)

**Date:** 2026-07-19 · **Companion:** `01-audit-findings.md` (gap IDs), `02-open-questions.md` (B-/NB- IDs)
**Reconciles with:** `../2026-07-18/consolidated/implementation-wave-plan.md` (Waves 0–6) and `release-gates.md`
(S0–S7, G0–G22). This restructures that track as **Mountains → Pebbles** with self-contained Cursor prompts, and
folds in the fresh 2026-07-19 findings. **Nothing here enables production real money** until `release-gates.md`
Go/No-Go says so.

## Planning posture (from the audit)

The launch-critical work is **DEPLOY → VERIFY → OPS → DECISIONS**, not BUILD (Output 1 §9). So the plan front-loads
promotion, sandbox money proof, automations, trust/security rollout, and observability; genuine build gaps (Bemba/Nyanja,
admin user-mgmt, search health, offline scanner, GMV cap) come **after** the money/trust path is proven. Video feed (M17)
stays deferred by design.

**Pebble types:** `[CODE]` = Cursor coding agent · `[OPS]` = founder/ops with dashboard/secret access (Cursor writes the
runbook + evidence template, a human executes) · `[DOC]` = docs only. Many launch blockers are `[OPS]` because they need
Lenco sandbox / Vercel / Supabase-dashboard / GHCR / Sentry access a coding agent does not have — this is faithful to the
corpus's NOT_AUDITABLE findings.

**Prompt convention (house style):** every Cursor prompt below is prepended in-tool with `prompts/_header.md` (project
one-liner, stack, folder map, tokens location, test/lint/typecheck commands) and ends with the standard **IMPLEMENTATION
REPORT** block from `.claude/commands/vergeo5.md` Phase 3. Design references live in `docs/designs/SELECTION.md` +
`docs/designs/TOKENS.md`; all UI consumes `@vergeo/ui` tokens (no ad-hoc colors) and is 360px-first.

---

## Mountains (5 launch + 1 post-verify)

| ID | Mountain | Outcome | Priority | Closes (audit) |
| -- | -------- | ------- | -------- | -------------- |
| **VM-A** | **Deployment & Schema Truth** | Live == repo: frontends on tip, DB migrations applied, API image pinned, CTA env set | **P0** | DL-1…DL-6, MR-S01/S11, MR-B10, G1/G9/G17 |
| **VM-B** | **Money & Escrow Verified** | Lenco **sandbox** MoMo+card→ledger, release accounting, refund, recon, false-success E2E — **STAGING_VERIFIED** | **P0** | MR-B01/B01b/B03, MR-C08, S1–S6, G3/G4 |
| **VM-C** | **Trust, KYC, Security & RBAC** | `0056`+orphan repair, FORCE RLS, role hook, demo exclusion, RBAC decided, legal artifact | **P0** | MR-D02/B11, MR-R01/R03, MR-S02, MR-A02, MR-L01, FD-02/03/04/06/07/08/12, G0/G11/G12/G13 |
| **VM-D** | **Automations Parity** | 17 dormant workflows activated + proven; backup workflow authored; money-workflow safety | **P0** | MR-W01/W02/W03/W04/W05, BG-5, G5/G7 |
| **VM-E** | **Observability, Ops & Launch QA** | Sentry, uptime, backup/restore drill, blocking CI, rollback, perf, E2E, VM isolation, go/no-go | **P0/P1** | MR-O01…O06, MR-R05, X-2/X-3/X-9, G6/G8/G9/G16/G19 |
| **VM-F** | **Vision Build Gaps** | Bemba/Nyanja, admin user-mgmt, search health, offline scanner, GMV cap, `multi_day`, locale de-route | **P1/P2** | BG-1/2/3/4, MR-B04/B07/V03, FD-05, NB-1 |

---

## Wave sequencing (parallel-safe within each wave; dispatch Wave N only after Wave N−1 PRs merge)

> **Parallel-safety rule:** no two pebbles in the same wave own the same file or migrate the same table. File/system
> ownership is disjoint per wave (proven in the pebble catalog's "Owns" column). Each pebble = one Cursor branch/PR
> titled `VM-x-Pnn: {title}`.

| Wave | Theme | Pebbles (parallel within wave) | Gate on entry |
| ---- | ----- | ------------------------------ | ------------- |
| **Wave 0** | Decisions + foundations (mostly non-code) | B-1…B-5 answers (FD log); VA-P00 backup artifact; VC-P08 legal engage; VD-P07/X-8 doc banners | — |
| **Wave 1** | Deployment & schema truth | VA-P01 promote FE ‖ VA-P02 apply migrations (staging) ‖ VA-P03 pin API ‖ VA-P04 CTA env | Wave 0 backup + B-2/B-3 |
| **Wave 2** | Money verify ‖ automations activate ‖ obs setup | VB-P01…P07 ‖ VD-P01…P06 ‖ VE-P01/P02 | Wave 1 (migrations applied, API pinned) |
| **Wave 3** | Trust/security rollout | VC-P01…P07, VC-P09 | Wave 1 + Wave 2 money proof + B-2/B-4/B-5 |
| **Wave 4** | Ops hardening & launch QA | VE-P03…P09 | Wave 2 (backup workflow) + Wave 3 |
| **Wave 5** | Vision build gaps | VF-P01…P07 | Money/trust path proven (Waves 2–4) |

Mapping to prior plan: Wave 1 ≈ old Wave 4 (deploy) + Wave 3 (DB); Wave 2 ≈ old Wave 1 (money) + Wave 2 (n8n);
Wave 3 ≈ old Wave 3 (KYC/RLS) + Wave 6 trust items; Wave 4 ≈ old Wave 5 (obs/CI); Wave 5 = new build-gap track.

---

## Pebble catalog

### VM-A — Deployment & Schema Truth (P0)

| Pebble | Type | Owns (files/systems) | Deps | Acceptance | Ref |
| ------ | ---- | -------------------- | ---- | ---------- | --- |
| VA-P00 | OPS | dated DB backup artifact + `…/vision-audit/evidence/backup-YYYYMMDD.md` | — | Backup taken **before** any migration; location+timestamp recorded | X-2, G7 |
| VA-P01 | OPS | Vercel promotions (customer/vendor/admin) + `evidence/deploy-promote.md` | Wave 0 | 3 prod SHAs = master tip; `/en\|fr\|zh/categories`→200; admin Access-gated; SHAs recorded | DL-1/2, G1/G17 |
| VA-P02 | OPS | migration apply runbook + `evidence/migrations-apply.md` (staging/branch first) | VA-P00, B-2/B-3 | `0051,0053,0054,0055,0056` applied in order on staging; `schema_migrations` matches target; no data loss | DL-3, MR-S01/S11, S0 |
| VA-P03 | OPS | API redeploy + `evidence/api-image.md` (GHCR digest) | — | API image digest recorded; `/admin/kyc/{id}/start-review` etc → 200 (not 404) on live | DL-5, MR-B10 |
| VA-P04 | OPS | Vercel env `NEXT_PUBLIC_VENDOR_APP_URL` on `convergeo-customer` | VA-P01 | Sell CTA href = `https://vendor.vergeo5.com…`; no "unavailable"; no `localhost` | DL-6, MR-C01, G10 |

### VM-B — Money & Escrow Verified (P0) — sandbox only, no prod money

| Pebble | Type | Owns | Deps | Acceptance | Ref |
| ------ | ---- | ---- | ---- | ---------- | --- |
| VB-P01 | OPS | `evidence/money-momo.md` | VA-P02/03, Lenco sandbox creds | Sandbox MoMo → `CHARGE_RECEIVED` + escrow-hold legs; ledger balanced; redacted Lenco match | MR-B01, S1, G3 |
| VB-P02 | OPS | `evidence/money-card.md` | ” | Sandbox card (Lenco widget) → ledger; same invariants | MR-B01, S2 |
| VB-P03 | OPS | `evidence/webhook-idempotency.md` | VB-P01 | Webhook replayed → single ledger txn (23505 dedupe proven) | MR-B01, G3 |
| VB-P04 | OPS | `evidence/release-accounting.md` | VB-P01 | `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; escrow→0; double-tick safe | MR-B01b, S3 |
| VB-P05 | OPS | `evidence/refund-matrix.md` | VB-P01 | Cancel→refund `rfd-*` payout + notify; refund idempotent; lane-1/lane-2 correct | MR-B03 |
| VB-P06 | OPS | `evidence/recon-alert.md` | VB-P01 | Forced Lenco-vs-ledger mismatch → actionable alert; no silent drift | MR-W05, G3 |
| VB-P07 | CODE | `e2e/specs/checkout-false-success.spec.ts` | VA-P01 | Pending/failed ≠ "paid"; COD ≤K500 never claims MoMo success; green in CI | MR-C08, S6, G4 |

### VM-C — Trust, KYC, Security & RBAC (P0)

| Pebble | Type | Owns | Deps | Acceptance | Ref |
| ------ | ---- | ---- | ---- | ---------- | --- |
| VC-P01 | OPS | `evidence/kyc-0056-rollout.md` | VA-P02, NB-14 | `0056` applied prod after staging PASS; orphan report run; **manual** repair only (no auto-upgrade) | MR-D02/B11, G12 |
| VC-P02 | CODE | `supabase/migrations/0057_force_rls_ticket_tiers.sql` | B-3 | FORCE RLS true on `ticket_type_instances`,`ticket_type_price_tiers`,`product_relations`; advisor clean; RLS tests green | MR-R01, FD-07, G0 |
| VC-P03 | OPS | `evidence/role-hook.md` (apply `0051`+enable Auth hook) | VA-P02, B-2 | JWT roles == `user_roles`; customer/vendor/admin isolation suites green | MR-S02, FD-03, G0 |
| VC-P04 | CODE | `services/api/tests/rls/test_matrix.py` (+ `test_no_untested_tables.py`) | — | `event_categories`,`product_relations`,`service_reviews` added to EXPECTATIONS; suite green | §5 hygiene |
| VC-P05 | CODE | `services/api/app/routers/refunds.py` | — | single `/admin/refunds/execute` mount under `AdminAuditedRoute`; direct mount removed; authz tests green | §5 hygiene |
| VC-P06 | CODE | `services/api/app/routers/search.py`, `catalog.py` + seed-label script | FD-04 | Demo (`demo/%`) excluded from public search/browse; labelled only on demo routes; test asserts exclusion | MR-D01, FD-04, G11 |
| VC-P07 | DOC/CODE | per B-4: `docs/ops/admin-access.md` (manual-ops) **or** admin RBAC schema+UI | B-4 | If single-admin: runbook for grant/revoke via guarded path; if additive: schema+RLS+UI+authz-matrix | MR-A02, FD-02, G15 |
| VC-P08 | OPS | `evidence/legal-signoff.md` | Wave 0 | Written Zambian-counsel DPA/NPS-Act escrow posture attached | MR-L01, FD-08, G13 |
| VC-P09 | OPS | Supabase Auth setting | — | Leaked-password protection enabled; advisor WARN cleared | MR-R03, G20 |

### VM-D — Automations Parity (P0)

| Pebble | Type | Owns | Deps | Acceptance | Ref |
| ------ | ---- | ---- | ---- | ---------- | --- |
| VD-P01 | OPS | activate `release-job.json`,`order-jobs.json` + `evidence/n8n-release.md` | VB-P04 | Active; authenticated tick succeeds; idempotent (no double-release); confirm-before-release ordering fixed | MR-W01, G5 |
| VD-P02 | OPS | activate `tickets-issue.json`,`tickets-release.json`,`event-release.json` + evidence | VB-P04 | Exactly-once ticket issue; dynamic-QR verifies; no double-issue at 60s tick | MR-W02, G5 |
| VD-P03 | OPS | activate 8 lifecycle workflows + `evidence/n8n-lifecycle.md` | Wave 1 | Each ticks once in test; abandoned-cart/funnel remain flag-gated OFF | MR-W03/W06 |
| VD-P04 | CODE+OPS | `infra/n8n/backup.json` + `docs/ops/n8n-workflows.md` row | — | Nightly dump workflow authored per `backup-schedule.md`; deployed; one successful dump | MR-W04, BG-5, G7 |
| VD-P05 | CODE | `infra/n8n/uptime-alert.json` + API `/webhook`/verify | — | `/webhook/uptime-alert` requires shared-secret/HMAC; unauthenticated POST rejected | §6 risk |
| VD-P06 | CODE | money workflow JSONs (`release-job`,`reconciliation`,`payment-sweeper`,`payout-failure-alert`) | VD-P01 | Error-workflow/retry + founder alert on non-2xx money ticks | §6 risk |
| VD-P07 | DOC | `docs/ops/n8n-workflows.md` | — | Document hidden `0 5 * * *` recon daily-report + `order-jobs` dual-endpoint | §6 minor |

### VM-E — Observability, Ops & Launch QA (P0/P1)

| Pebble | Type | Owns | Deps | Acceptance | Ref |
| ------ | ---- | ---- | ---- | ---------- | --- |
| VE-P01 | OPS | Sentry projects + DSN envs + `evidence/sentry.md` | — | Vergeo5 projects exist (customer/vendor/admin/API); test error ingested; release tags | MR-O01, G6 |
| VE-P02 | OPS | UptimeRobot monitors + `evidence/uptime.md` | — | Monitors green on customer/api/vendor/admin health | MR-O02, G6 |
| VE-P03 | OPS | `evidence/restore-drill.md` | VD-P04 | Scratch restore from backup succeeds; RPO/RTO documented | MR-O04, G7 |
| VE-P04 | CODE | `.github/workflows/ci.yml` | — | `secret-scan` blocking (`continue-on-error` removed); branch protection confirmed | MR-R05, G8 |
| VE-P05 | OPS | `evidence/rollback-drill.md` | VA-P01/03 | Timed Vercel + API rollback dry-run recorded | G9 |
| VE-P06 | CODE | `.github/workflows/perf.yml`, `lighthouserc.json` | VA-P01 | Budgets enforced (≤150KB gz, LCP≤2.5s, Perf≥90/SEO≥95/A11y≥95) or documented waiver | MR-O06, G19 |
| VE-P07 | CODE | `e2e/specs/critical-path.spec.ts` | VA-P01 | Browse→cart→checkout(sandbox)→confirm green; distinct file from VB-P07 | G16 |
| VE-P08 | OPS | `evidence/env-isolation-plan.md` | NB-8 | Plan (or execution) to isolate Vergeo5 API/n8n from shared WAHA/ZedApply VM | X-9, NB-8 |
| VE-P09 | OPS | `release-gates.md` evidence pack | Waves 1–4 | Go/No-Go pack filled; maturity per area recorded | release-gates |

### VM-F — Vision Build Gaps (P1/P2 — after money/trust proven)

| Pebble | Type | Owns | Deps | Acceptance | Ref |
| ------ | ---- | ---- | ---- | ---------- | --- |
| VF-P01 | CODE | `packages/i18n/messages/bem/*`, `packages/i18n/messages/nya/*` | — | 16 namespaces filled (human-reviewed) for `bem`,`nya`; i18n-lint passes; core flows render vernacular | BG-1, G18 |
| VF-P02 | CODE | locale switcher component + `packages/i18n/src/locales.ts` config | NB-1 | `zh` removed from public locale switcher (kept for QA) until market decision; EN/FR + bem/nya public | NB-1 |
| VF-P03 | CODE/DOC | per B-4 (admin user-mgmt) | B-4, VC-P07 | Build grant/revoke UI **or** documented manual-ops path; audit trail | BG-2 |
| VF-P04 | CODE | `services/api/app/routers/search.py`, `services/api/app/services/embeddings/*` | — | `/search` returns `degraded=false` on common queries; embeddings/FTS health fixed | MR-B07 |
| VF-P05 | CODE | `apps/vendor/sw-scanner.ts` + scan components | — | Tickets cached offline; scan works offline then syncs; first-scan-wins | MR-V03, BG-4 |
| VF-P06 | CODE | `services/api/app/services/events/*` + tests | — | Organiser Tier-1 GMV cap enforced; over-cap rejected + audited | MR-B04, BG-3 |
| VF-P07 | DOC | `docs/plan/00-decisions.md` + event copy | FD-05 | `multi_day` accepted as `standard`+`ends_at`; docs/UI consistent; no enum churn | FD-05, MR-S08 |

---

## Cursor prompts

> Each prompt is self-contained per house style: prepend `prompts/_header.md`, append the IMPLEMENTATION REPORT block.
> `[OPS]` prompts are runbook+evidence tasks — a Cursor agent writes the evidence doc/scripts and the founder executes the
> privileged step, pasting redacted proof. Prompts cite the audit row they close and end with acceptance criteria.

### Wave 0 — decisions + foundations

#### VA-P00 · Pre-migration backup artifact `[OPS]`
**Prepend** `prompts/_header.md`. **Closes:** X-2, G7 (backup-before-DDL rule).
**Context:** No dated backup exists; VM-A/VM-C apply 6 migrations. A backup MUST precede any DDL.
**Task:** Take a full logical dump of Supabase `dpadrlxukcjbewpqympu` (or trigger the platform PITR snapshot); Cursor writes the runbook + evidence stub, founder runs the dump and pastes location/timestamp (no secrets).
**Owns:** `docs/production-readiness/2026-07-19/vision-audit/evidence/backup-YYYYMMDD.md`.
**Acceptance:** Dated artifact recorded (location + size + checksum), timestamp **before** VA-P02 runs. **Report** block.

#### Wave-0 decisions `[DOC]`
Record answers to **B-1…B-5** (release strategy, role hook, FORCE RLS, admin RBAC, catalogue scope) using the log template in `02-open-questions.md`; mirror into `docs/plan/00-decisions.md` + `source-conflicts-and-decisions.md` §5. No code. Also action **VC-P08** (legal engagement) and **VD-P07/X-8** doc SoT banners in parallel.

---

### Wave 1 — deployment & schema truth

#### VA-P01 · Promote frontends to master tip `[OPS]`
**Prepend** `_header.md`. **Closes:** DL-1/DL-2, G1/G17.
**Context:** Customer prod = `cc4a824` (#296); `/en|fr|zh/categories` → 500 (digest `3012388270`); #298 fix + #302 live-beta not promoted. Vendor/admin prod SHA unconfirmed since `8cc1fa0`.
**Task:** Promote Vercel `convergeo-customer/vendor/admin` to current master tip (or merge #302 first per B-1); record each prod deployment id + `githubCommitSha`; re-probe routes.
**Owns:** `…/evidence/deploy-promote.md` only (no app code).
**Acceptance:** 3 prod SHAs == master tip; `/en|fr|zh/categories` → 200 (honest empty allowed, **not** digest `3012388270`); vendor/admin health gated; SHAs recorded. **Report** block.

#### VA-P02 · Apply migrations 0051/0053–0056 (staging-first) `[OPS]`
**Prepend** `_header.md`. **Closes:** DL-3, MR-S01/S11, S0/G0 (schema).
**Context:** Live applied ≤`0050` + odd `20260717100303`(=`0052`). Repo has through `0056`. Role hook, translation_overrides, service reviews/bookable, KYC integrity all absent live.
**Task:** On an **identifier-distinct staging/branch DB first**, apply `0051`,`0053`,`0054`,`0055`,`0056` **in order**; verify objects (`custom_access_token*`, `translation_overrides`, `services.bookable`, KYC trigger/view). Cursor writes the apply script + verification SQL; founder runs after VA-P00 backup.
**Owns:** `…/evidence/migrations-apply.md` + `scripts/db/apply-0051-0056.sql` (idempotent guards).
**Acceptance:** staging `schema_migrations` matches agreed target incl `0056`; object checks pass; legacy `kyc pending→submitted` handled; **no prod apply yet** (prod apply is VC-P01). **Report** block.

#### VA-P03 · Pin & redeploy API image `[OPS]`
**Prepend** `_header.md`. **Closes:** DL-5, MR-B10.
**Context:** API SHA NOT_AUDITABLE (GHCR auth); OpenAPI reports `0.1.0`; KYC lifecycle routes 404'd on live host (07-18) → deployed API lags master.
**Task:** Read GHCR digest for `ghcr.io/kalumuso/convergeo-api`; set `API_IMAGE_TAG` to the master-built image; redeploy via `infra/redeploy-api.sh`; confirm `/admin/kyc/{id}/start-review|suspend|revoke` return 200 (authed), not 404.
**Owns:** `…/evidence/api-image.md` (+ `infra/redeploy-api.sh` only if a fix is needed).
**Acceptance:** image digest recorded in release ledger; KYC lifecycle routes live; `/healthz`,`/readyz` 200. **Report** block.

#### VA-P04 · Set vendor-app URL env `[OPS]`
**Prepend** `_header.md`. **Closes:** DL-6, MR-C01, G10.
**Context:** Sell CTAs disabled ("temporarily unavailable"); `NEXT_PUBLIC_VENDOR_APP_URL` unset in customer prod (code fail-closed).
**Task:** Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer`; redeploy; verify CTA.
**Owns:** Vercel env (no repo code) + `…/evidence/cta.md`.
**Acceptance:** `/en/sell` CTA href → `https://vendor.vergeo5.com…`; no "unavailable"; no `localhost`. **Report** block.

---

### Wave 2 — money verify ‖ automations ‖ observability setup

#### VB-P01 · Sandbox MoMo → ledger `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-B01, S1, G3.
**Context:** `settle_prepaid_collection`→`CHARGE_RECEIVED` is CODE_COMPLETE (#274) but 0 payments/0 ledger live — never STAGING_VERIFIED.
**Task:** With Lenco **sandbox** creds on the isolated stack, run a MoMo prepaid checkout; capture `payments` + `ledger_transactions`/`ledger_postings` aggregates; confirm balanced legs (charge −gross, escrow hold) and idempotent replay. Redact PII/refs.
**Owns:** `…/evidence/money-momo.md` (+ `load/invariant-check.py` invocation).
**Acceptance:** MoMo sandbox pay → `CHARGE_RECEIVED` + hold; ledger zero-sums; redacted Lenco match attached; **no prod money**. **Report** block.

#### VB-P02 · Sandbox card → ledger `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-B01, S2. Same as VB-P01 for the Lenco hosted **card** widget path (`payments_card`). **Owns:** `…/evidence/money-card.md`. **Acceptance:** card sandbox pay → balanced ledger; no false-success. **Report** block.

#### VB-P03 · Webhook replay idempotency `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-B01, G3. **Task:** replay a Lenco webhook (same event id) against sandbox; assert single ledger txn (`webhook_events` unique / `23505` dedupe). **Owns:** `…/evidence/webhook-idempotency.md`. **Acceptance:** one txn on replay; bad signature → 401. **Report** block.

#### VB-P04 · Release accounting drill `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-B01b, S3. **Task:** on sandbox order, run escrow release tick; assert `COMMISSION_CAPTURE` posts before `RELEASE_TO_VENDOR`, escrow nets to 0, double-tick captures once. **Owns:** `…/evidence/release-accounting.md`. **Acceptance:** #294 A1–A8 invariants proven. **Report** block.

#### VB-P05 · Refund / cancel matrix `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-B03. **Task:** cancel + refund a sandbox order; assert `rfd-*` payout row (stable idempotency key), notify enqueued, lane-1/lane-2 math correct, idempotent on retry. **Owns:** `…/evidence/refund-matrix.md`. **Acceptance:** refund policy matches code; no double payout. **Report** block.

#### VB-P06 · Reconciliation mismatch alert `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-W05, G3. **Task:** force a Lenco-vs-ledger mismatch on sandbox; confirm the recon cron produces an actionable alert (not silent). **Owns:** `…/evidence/recon-alert.md`. **Acceptance:** mismatch alerted; report row written. **Report** block.

#### VB-P07 · False-success E2E `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-C08, S6, G4.
**Context:** UI hardening CODE_COMPLETE (#289) but no E2E proves pending/failed ≠ paid.
**Task:** Playwright specs: abandoned MoMo (pending) never shows "paid"; delayed webhook only flips after confirmed policy; COD ≤K500 never claims MoMo success. Run against the sandbox stack.
**Owns:** `e2e/specs/checkout-false-success.spec.ts` only.
**Acceptance:** specs green in CI; each false-success path asserted. **Report** block.

#### VD-P01 · Activate escrow auto-release workflows `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-W01, G5.
**Context:** `release-job.json`,`order-jobs.json` committed but n8n has only 2 active workflows.
**Task:** Import/activate `release-job` (+`order-jobs`) with `INTERNAL_RELEASE_JOB_TOKEN`/`INTERNAL_ORDER_JOBS_TOKEN`; fix `order-jobs` fan-out so auto-confirm precedes auto-release; prove one authenticated tick + idempotent release on sandbox.
**Owns:** `infra/n8n/release-job.json`,`infra/n8n/order-jobs.json` + `…/evidence/n8n-release.md`.
**Acceptance:** workflows active; tick 200; no double-release; execution IDs recorded. **Report** block.

#### VD-P02 · Activate ticket issuance/release workflows `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-W02, G5.
**Task:** Activate `tickets-issue`,`tickets-release`,`event-release`; prove exactly-once issuance (60s tick), dynamic-QR verifies, no double-issue; distinct tokens.
**Owns:** `infra/n8n/tickets-issue.json`,`tickets-release.json`,`event-release.json` + `…/evidence/n8n-tickets.md`.
**Acceptance:** exactly-once ticket on sandbox paid order; QR+PIN verify. **Report** block.

#### VD-P03 · Activate lifecycle workflows `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-W03/W06.
**Task:** Activate `kyc-nudge`,`payout-failure-alert`,`low-stock-alert`,`review-request`,`reservation-sweeper`,`embeddings-cron`,`analytics-retention`,`admin-digest`; keep `abandoned-cart`/`funnel-abandon` flag-gated OFF; prove each ticks once.
**Owns:** those 8 `infra/n8n/*.json` + `…/evidence/n8n-lifecycle.md`.
**Acceptance:** each fires once in test; digest reaches founder WhatsApp; no money touched. **Report** block.

#### VD-P04 · Author + deploy DB backup workflow `[CODE+OPS]`
**Prepend** `_header.md`. **Closes:** MR-W04, BG-5, G7.
**Context:** `backup-schedule.md` specs a nightly dump but **no JSON exists**.
**Task:** Author `infra/n8n/backup.json` (cron `0 2 * * *` Africa/Lusaka → Execute-Command `scripts/db-dump.sh` → OCI Object Storage; failure-alert branch); register in `docs/ops/n8n-workflows.md`; deploy + one successful dump.
**Owns:** `infra/n8n/backup.json`, `docs/ops/n8n-workflows.md`, `scripts/db-dump.sh` (if absent).
**Acceptance:** workflow active; one dated dump artifact produced; failure branch alerts. **Report** block.

#### VD-P05 · Authenticate uptime-alert webhook `[CODE]`
**Prepend** `_header.md`. **Closes:** §6 risk (unauth founder-page vector).
**Task:** Add a shared-secret/HMAC check on `/webhook/uptime-alert` (n8n node + verifying header); reject unauthenticated POSTs.
**Owns:** `infra/n8n/uptime-alert.json` (+ a verify note in `docs/ops/observability.md`).
**Acceptance:** unauthenticated POST rejected; UptimeRobot configured with the secret; founder page only on authed down-alert. **Report** block.

#### VD-P06 · Money-workflow error alerting `[CODE]`
**Prepend** `_header.md`. **Closes:** §6 risk (silent money-tick failures).
**Task:** Add an error-workflow / retry + founder alert on non-2xx for `release-job`,`reconciliation`,`payment-sweeper`,`payout-failure-alert`.
**Owns:** those 4 `infra/n8n/*.json` (disjoint from VD-P01's set? — `release-job` overlaps VD-P01: sequence VD-P06 **after** VD-P01 in the same track, not parallel on that file).
**Acceptance:** a forced 500 on a money tick pages the founder; retry/backoff applied. **Report** block.

#### VE-P01 · Sentry projects + DSNs `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-O01, G6.
**Task:** Create Vergeo5 Sentry projects (customer/vendor/admin/API) under `convergeo-w2`; set `SENTRY_DSN`/`NEXT_PUBLIC_SENTRY_DSN` per app; fire a test error each.
**Owns:** Sentry config + `…/evidence/sentry.md` (DSNs via env, not repo).
**Acceptance:** 4 projects exist; test event visible per app; release tags match SHAs. **Report** block.

#### VE-P02 · Uptime monitors `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-O02, G6. **Task:** UptimeRobot monitors on customer/api/vendor/admin health (+ wire to VD-P05 webhook). **Owns:** `…/evidence/uptime.md`. **Acceptance:** monitors green; down → founder page. **Report** block.

---

### Wave 3 — trust / security rollout

#### VC-P01 · Apply `0056` prod + KYC orphan repair `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-D02/B11, G12; NB-14.
**Context:** `0056` staging-verified in VA-P02; live has 3 orphaned-tier vendors, 0 kyc_records; #293 freezes privileges but does not auto-heal.
**Task:** Apply `0056` to prod (order: API understands statuses → migrate → clients); run `/admin/kyc/orphaned-tiers` report; perform **manual, guarded** repair per orphan (proper submission→approve, or clear tier via guarded path). **Never** `UPDATE vendors SET kyc_tier` and **never** auto-upgrade.
**Owns:** `…/evidence/kyc-0056-rollout.md`.
**Acceptance:** `0056` in prod `schema_migrations`; orphan report attached; each orphan ticketed+resolved manually; privileges freeze without approved record. **Report** block.

#### VC-P02 · FORCE RLS on ticket-tier + product_relations `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-R01, FD-07, G0.
**Task:** Additive migration setting `relforcerowsecurity=true` on `ticket_type_instances`,`ticket_type_price_tiers`,`product_relations`; fix any table-owner/service-role assumption; re-run advisor + RLS matrix.
**Owns:** `supabase/migrations/0057_force_rls_ticket_tiers.sql` + matching RLS test additions.
**Acceptance:** advisor shows force true; isolation tests green; no service-role regression. **Report** block.

#### VC-P03 · Role hook (`0051`) enable `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-S02, FD-03, G0.
**Task:** After VA-P02, enable the Supabase Auth custom-access-token hook; verify JWT `roles` == `user_roles`; run customer/vendor/admin isolation suites.
**Owns:** `…/evidence/role-hook.md`.
**Acceptance:** JWT/`user_roles` consistent; isolation green; middleware no longer relies on stale `app_metadata`. **Report** block.

#### VC-P04 · Close RLS test-matrix registry gap `[CODE]`
**Prepend** `_header.md`. **Closes:** §5 hygiene.
**Task:** Add `event_categories`,`product_relations`,`service_reviews` to `EXPECTATIONS` (table×persona×verb) so `test_no_untested_tables.py` passes with them present.
**Owns:** `services/api/tests/rls/test_matrix.py`, `services/api/tests/rls/test_no_untested_tables.py`.
**Acceptance:** RLS suite green; no untested live table. **Report** block.

#### VC-P05 · Collapse duplicate `/refunds/execute` mount `[CODE]`
**Prepend** `_header.md`. **Closes:** §5 hygiene.
**Task:** Remove the direct `/refunds/execute` mount; keep only `/admin/refunds/execute` under `AdminAuditedRoute`; update tests/clients.
**Owns:** `services/api/app/routers/refunds.py` (+ callers).
**Acceptance:** single admin-audited mount; authz + audit tests green; no client breakage. **Report** block.

#### VC-P06 · Exclude demo catalogue from public search `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-D01, FD-04, G11.
**Context:** 134 `demo/%` listings are public-eligible (D25 requires exclusion).
**Task:** Filter demo vendors/listings out of public search/browse/home; keep labelled fixtures only on demo routes; add a test asserting demo rows never appear in public `/search` or `/catalog`.
**Owns:** `services/api/app/routers/search.py`, `services/api/app/routers/catalog.py`, seed-label script.
**Acceptance:** public search excludes `demo/%`; demo visible only on demo route; test proves it. **Report** block.

#### VC-P07 · Admin RBAC per B-4 `[DOC or CODE]`
**Prepend** `_header.md`. **Closes:** MR-A02, FD-02, G15.
**Task (default single-admin):** write `docs/ops/admin-access.md` runbook for grant/revoke via guarded path + CF Access; **do not invent superadmin/moderator**. If B-4 elected additive roles: additive migration + RLS + grant/revoke API/UI + authz-matrix tests.
**Owns:** `docs/ops/admin-access.md` (default) — else the RBAC schema/UI files.
**Acceptance:** matches B-4 decision; no fabricated role UI; authz matrix consistent. **Report** block.

#### VC-P09 · Enable leaked-password protection `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-R03, G20. **Task:** enable in Supabase Auth; confirm advisor cleared. **Owns:** `…/evidence/auth-hardening.md`. **Acceptance:** advisor WARN gone. **Report** block.

---

### Wave 4 — ops hardening & launch QA

#### VE-P03 · Restore drill `[OPS]`
**Prepend** `_header.md`. **Closes:** MR-O04, G7. **Task:** restore VD-P04's dump into a scratch DB; verify integrity; document RPO/RTO. **Owns:** `…/evidence/restore-drill.md`. **Acceptance:** restore succeeds; RPO/RTO recorded. **Report** block.

#### VE-P04 · Make secret-scan blocking `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-R05, G8. **Task:** remove `continue-on-error:true` from `secret-scan`; align `docs/ops/ci.md`; confirm branch protection requires it. **Owns:** `.github/workflows/ci.yml`, `docs/ops/ci.md`. **Acceptance:** a planted secret fails CI; merges blocked. **Report** block.

#### VE-P05 · Rollback drill `[OPS]`
**Prepend** `_header.md`. **Closes:** G9. **Task:** dry-run Vercel rollback (prior deployment) + API image tag rollback; time it. **Owns:** `…/evidence/rollback-drill.md`. **Acceptance:** timed procedure recorded per `infra/ROLLBACK.md`. **Report** block.

#### VE-P06 · Enforce Lighthouse budgets `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-O06, G19. **Task:** make `perf.yml` budgets enforcing (drop advisory); re-probe customer routes at 360px/Fast-3G. **Owns:** `.github/workflows/perf.yml`, `lighthouserc.json`. **Acceptance:** ≤150KB gz, LCP≤2.5s, Perf≥90/SEO≥95/A11y≥95 or documented waiver. **Report** block.

#### VE-P07 · Critical-path E2E `[CODE]`
**Prepend** `_header.md`. **Closes:** G16. **Task:** Playwright happy-path browse→cart→checkout(sandbox)→confirm across customer app. **Owns:** `e2e/specs/critical-path.spec.ts` (distinct file from VB-P07). **Acceptance:** green in CI on sandbox stack. **Report** block.

#### VE-P08 · Environment isolation plan `[OPS]`
**Prepend** `_header.md`. **Closes:** X-9, NB-8. **Task:** document (and schedule) moving Vergeo5 API/n8n off the shared VM that also hosts WAHA + ZedApply `zedcv-backend`; confirm WhatsApp Cloud-API sender number is separate from any WAHA sender (NB-7). **Owns:** `…/evidence/env-isolation-plan.md`. **Acceptance:** isolation plan with owner+date; number-separation confirmed. **Report** block.

#### VE-P09 · Go/No-Go evidence pack `[OPS]`
**Prepend** `_header.md`. **Closes:** release-gates. **Task:** fill the `release-gates.md` release-evidence template from Waves 1–4 outputs; record per-area maturity (CODE/STAGING/PRODUCTION_VERIFIED). **Owns:** `…/evidence/go-no-go-YYYYMMDD.md`. **Acceptance:** every S/G gate has a PASS/FAIL with evidence pointer; no PASS from CODE_COMPLETE alone. **Report** block.

---

### Wave 5 — vision build gaps (after money/trust proven)

#### VF-P01 · Bemba/Nyanja translations `[CODE]`
**Prepend** `_header.md`. **Closes:** BG-1, G18.
**Context:** `bem`/`nya` have only `notifications.json`; 16 namespaces fall back to EN. `admin/translations` TranslatorView exists to author them.
**Task:** Fill all 16 `bem` + `nya` namespaces (human-reviewed, ICU-valid); ensure i18n-lint + pseudo-locale checks pass; verify core flows render vernacular.
**Owns:** `packages/i18n/messages/bem/*`, `packages/i18n/messages/nya/*`.
**Acceptance:** namespaces complete; i18n-lint green; core customer flows readable in bem/nya. **Report** block.

#### VF-P02 · De-route `zh` from public switcher `[CODE]`
**Prepend** `_header.md`. **Closes:** NB-1.
**Task:** Pending a market decision on Chinese, keep `zh` building (QA fidelity) but remove it from the public locale switcher; public switcher shows EN, FR, + bem/nya (once VF-P01 lands).
**Owns:** locale switcher component + `packages/i18n/src/locales.ts` (public-locale list).
**Acceptance:** `zh` absent from public switcher; still resolvable for QA; no route 404s. **Report** block.

#### VF-P03 · Admin user/role management per B-4 `[CODE/DOC]`
**Prepend** `_header.md`. **Closes:** BG-2. Follows VC-P07: if single-admin, ship the documented manual-ops tooling; if additive roles elected, ship grant/revoke UI with audit trail + authz-matrix tests. **Owns:** admin RBAC UI files or `docs/ops/admin-access.md` extension. **Acceptance:** matches B-4; audit trail on every role change. **Report** block.

#### VF-P04 · Fix search `degraded=true` `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-B07.
**Task:** Diagnose why `/search` reports `degraded=true` (embeddings backlog / FTS / RRF lane failure); fix so common queries return `degraded=false`.
**Owns:** `services/api/app/routers/search.py`, `services/api/app/services/embeddings/*`.
**Acceptance:** representative queries `degraded=false`; RRF lanes healthy; test asserts non-degraded. **Report** block.

#### VF-P05 · Offline scanner cache + scan-sync `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-V03, BG-4.
**Task:** Cache event tickets in the vendor scanner SW for offline verification; queue scans and sync on reconnect; enforce first-scan-wins.
**Owns:** `apps/vendor/sw-scanner.ts` + `apps/vendor/app/**/events/[id]/scan/_components/*`.
**Acceptance:** scan works offline; sync reconciles; duplicate offline scan loses to first. **Report** block.

#### VF-P06 · Organiser Tier-1 GMV fraud cap `[CODE]`
**Prepend** `_header.md`. **Closes:** MR-B04, BG-3.
**Task:** Enforce the Tier-1 organiser GMV cap (~K20k) before paid-event escrow; reject/hold over-cap with audit.
**Owns:** `services/api/app/services/events/*` + tests.
**Acceptance:** over-cap organiser rejected + audited; cap value in config; failure-path test. **Report** block.

#### VF-P07 · Event `multi_day` doc reconciliation `[DOC]`
**Prepend** `_header.md`. **Closes:** FD-05, MR-S08. **Task:** per B-4/FD-05 default, document `multi_day` as `standard`+`ends_at`; align events copy/docs; no enum churn. **Owns:** `docs/plan/00-decisions.md` + events copy notes. **Acceptance:** docs/UI consistent; no schema change. **Report** block.

---

## Dispatch checklist (per wave)

1. Confirm Wave N−1 PRs merged + evidence attached.
2. Verify no two in-flight pebbles own the same file (catalog "Owns" column).
3. Dispatch each pebble as `VM-x-Pnn: {title}` on its own branch.
4. Collect IMPLEMENTATION REPORTs; review per `.claude/commands/vergeo5.md` Phase 4 (heightened scrutiny on money/authz/RLS/idempotency).
5. Update `docs/plan/00-status.md` + `release-gates.md` gate results. Do **not** flip `public_launch` / real-money flags outside VE-P09 Go/No-Go.

