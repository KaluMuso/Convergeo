# Current Implementation Board — 2026-07-20

**Purpose:** Evidence-based production-readiness board for execution **before** further runtime/product changes.  
**Master tip assessed:** `b1ea6a3` (Merge PR #355)  
**Live probes (same day):** Supabase project `dpadrlxukcjbewpqympu`, n8n MCP, Vercel deployments.  
**Companions:** `gap-analysis-vs-docs.md`, `master-vs-docs-representation-report.md`, `docs/plan/00-status.md`, `docs/plan/launch-checklist.md`, `docs/production-readiness/2026-07-18/consolidated/release-gates.md`, `docs/production-readiness/2026-07-19/vision-audit/`.

**Do not reimplement:** `refunds.source_key` / repo file `supabase/migrations/0063_refunds_source_key_uniq.sql` (merged via PR #352). Ops must **apply** that SQL to live after resolving the version collision below — not rewrite the feature.

---

## 0. Fingerprint (verified)

| Surface                    | Evidence @ board time                                                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `origin/master`            | `b1ea6a3` — includes #350, #351, #352, #353, #355                                                                                      |
| Customer Vercel production | READY @ `b1ea6a3` (DL-1 closed at tip)                                                                                                 |
| Vendor Vercel production   | READY @ `1d137ae` (#351); docs-only tip lag (#353/#355) — non-runtime                                                                  |
| Live DB migrations         | Through timestamped `0062_payments_checkout_success_uniq` **plus** live-only name `0063_revoke_execute_review_reply_guards`            |
| Live `refunds.source_key`  | **Absent** — column missing; index still `refunds_order_id_active_uniq`                                                                |
| Live money/KYC rows        | `payments=0`, `ledger_transactions=0`, `orders=0`, `kyc_records=0`                                                                     |
| Live FORCE RLS             | `order_money_gates`/`payments`/`refunds` = true; **`ticket_type_instances` / `ticket_type_price_tiers` / `product_relations` = false** |
| n8n live                   | **2 workflows**, both active: notification dispatch; payment reconciliation crons                                                      |
| Repo n8n JSON              | 19 files under `infra/n8n/*.json`; backup is `backup-schedule.md` only (no `backup.json`)                                              |

### Critical migration collision (blocks naive “apply 0063”)

| Plane               | Version / name                                  | Content                                         |
| ------------------- | ----------------------------------------------- | ----------------------------------------------- |
| **Repo master**     | `0063_refunds_source_key_uniq.sql` (#352)       | Adds `refunds.source_key` + partial unique      |
| **Live DB**         | `0063_revoke_execute_review_reply_guards`       | Revokes EXECUTE on review-reply guards          |
| **Unmerged branch** | `claude/convergeo-bug-audit-nu1g4b` @ `9d146cc` | Same revoke SQL applied live; **not** on master |

**Implication:** Live already consumed the `0063` ledger slot for revoke hygiene. Repo `0063` (source_key) has **not** been applied. Closing this needs a **numbering reconcile PR** (land revoke file to match live + renumber source_key → `0064` **without changing SQL semantics**), then apply source_key to live. Do **not** invent a second source_key design.

---

## 1. Reconciliation of the two July 20 reports

| Topic           | Gap analysis (`gap-analysis-vs-docs.md`) | Representation report (`master-vs-docs-representation-report.md`) | Board reconciliation                                                                                              |
| --------------- | ---------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Assessed tip    | Pre-#352 (“#352 pending”)                | `1d137ae` (#351); #352/#353 unmerged                              | Both **stale** vs `b1ea6a3` (#352/#353/#355 merged)                                                               |
| BUILD %         | ~86% (min of BUILD∩DEPLOY∩VERIFY)        | ~93% (code fidelity to v1 docs)                                   | Different definitions — both valid; use **93% code / ~86% min-lens** as dual view                                 |
| READINESS %     | ~42% overall; ~25% real-money            | ~31–40% readiness corpus                                          | Prefer **31–40%** for gate/pebble completion; ~42% understates deploy progress if migrations `0057–0062` now live |
| Live migrations | “`0057–0062` may lag”                    | Unverified (Supabase unauth); assumed lag past `0056`             | **Updated:** `0057–0062` **are applied**; residual is **source_key** + numbering collision + FORCE RLS            |
| Frontend deploy | Historical SHA lag / categories 500      | DL-1/DL-2 closed at `1d137ae`                                     | **Updated:** customer prod @ **`b1ea6a3`**; vendor prod @ `1d137ae`                                               |
| #352 / returns  | “Merge #352” still in next program       | Listed unmerged                                                   | **ALREADY_CLOSED** in repo; **DEPLOYMENT_REQUIRED** for live schema                                               |
| n8n             | 2/19 active                              | 2/19 active                                                       | **Confirmed** still 2                                                                                             |
| Money rows      | Empty                                    | Empty (07-19)                                                     | **Confirmed** still empty                                                                                         |

**Blended headline for execution:** code ~90–93% of v1; production-ready per gates **~30–40%**; browse-safe invite beta **conditional**; real money / `public_launch` **NO-GO**.

---

## 2. Status categories (legend)

| Category                     | Meaning                                                                             |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| `REPO_CLOSABLE`              | Code/docs/CI change on a PR closes the item                                         |
| `DEPLOYMENT_REQUIRED`        | Artifact exists (or will after a tiny reconcile); must apply/import/promote on live |
| `LIVE_VERIFICATION_REQUIRED` | Needs sandbox/staging/live drill + evidence pack                                    |
| `FOUNDER_REQUIRED`           | Founder account/credential/ops action                                               |
| `LEGAL_REQUIRED`             | Counsel / written legal artifact                                                    |
| `DELIBERATELY_DEFERRED`      | Locked out of v1 / post-launch by decision                                          |
| `ALREADY_CLOSED`             | Done on master and/or live with evidence                                            |
| `STALE_DOCUMENTATION`        | Doc claim wrong vs current evidence — fix docs only                                 |

---

## 3. Board inventory

Each item: gap/gate · priority · status · evidence · files · deps · acceptance · verify · browse-beta / real-money / `public_launch` blockers · PR boundary.

### 3.A ALREADY_CLOSED

#### AC-01 — Checkout single-settle (#350)

- **Gate / gap:** G3 / money hardening
- **Priority:** P0 (was)
- **Status:** `ALREADY_CLOSED`
- **Evidence:** `f1805f6` / merge `c7e7f7b`; migration `0062_payments_checkout_success_uniq.sql` **applied live** (`schema_migrations` name `0062_payments_checkout_success_uniq`)
- **Files:** n/a (no further change)
- **Deps:** none
- **Acceptance:** one SUCCESS payment / checkout group; no double `CHARGE_RECEIVED`
- **Verify:** `uv run pytest` money suites; live index present
- **Blocks browse-beta / real-money / public_launch:** no / no (code) / no
- **PR boundary:** none — do not reopen

#### AC-02 — Item-refund remainder release (#351)

- **Gate / gap:** G3 / escrow
- **Priority:** P0 (was)
- **Status:** `ALREADY_CLOSED`
- **Evidence:** merge `1d137ae`; remainder release + gate promote in escrow code/tests
- **Files:** n/a
- **Deps:** none
- **Acceptance:** partial PRE_RELEASE does not strand remaining escrow
- **Verify:** unit/DB tests on master CI
- **Blocks:** no / no / no
- **PR boundary:** none

#### AC-03 — `refunds.source_key` uniqueness (#352) — **repo only**

- **Gate / gap:** returns / MR-B03
- **Priority:** P0
- **Status:** `ALREADY_CLOSED` (repo); live apply tracked separately as DEP-02
- **Evidence:** merge `496819b`; file `supabase/migrations/0063_refunds_source_key_uniq.sql` on master; CI seed fix `7e886d2`
- **Files:** do **not** rewrite feature
- **Deps:** DEP-01 numbering reconcile before live apply
- **Acceptance:** source_key column + `refunds_source_key_active_uniq` on master schema replay
- **Verify:** `supabase db reset` / migration replay CI
- **Blocks:** no / **yes until live** / yes until live
- **PR boundary:** none for reimplementation

#### AC-04 — Gap analysis + representation docs (#353 / #355)

- **Gate / gap:** documentation
- **Priority:** P2
- **Status:** `ALREADY_CLOSED`
- **Evidence:** merges `69e6a7a`, `b1ea6a3`; files under `docs/production-readiness/2026-07-20/`
- **Blocks:** no / no / no
- **PR boundary:** none (this board supersedes stale % / tip claims)

#### AC-05 — F1 domain

- **Gate / gap:** F1
- **Priority:** P0
- **Status:** `ALREADY_CLOSED`
- **Evidence:** `launch-checklist.md` F1 checked; vergeo5.com live
- **Blocks:** no / no / no

#### AC-06 — Beta / `public_launch` flag path + invoicing / prohibited

- **Gate / gap:** M16-P09 / M15
- **Priority:** P0–P1
- **Status:** `ALREADY_CLOSED` (build)
- **Evidence:** `0030_beta_invites`, `test_beta.py`, gapless invoice tests, `test_prohibited.py`
- **Blocks:** no / no / flip still FOUNDER after gates

#### AC-07 — Customer prod at tip (DL-1)

- **Gate / gap:** DL-1 / G1
- **Priority:** P0
- **Status:** `ALREADY_CLOSED`
- **Evidence:** Vercel `convergeo-customer` production `githubCommitSha=b1ea6a3`
- **Blocks:** no / no / no

#### AC-08 — Live migrations `0057`–`0062`

- **Gate / gap:** DL-3 reopen / G9
- **Priority:** P0
- **Status:** `ALREADY_CLOSED`
- **Evidence:** Supabase `list_migrations` includes `0057`…`0062` (2026-07-20 timestamps)
- **Note:** supersedes 07-19 “stuck at 0056” and gap-analysis “may lag 0057–0062”

#### AC-09 — Internal cron token fail-closed + money hardening trail

- **Gate / gap:** G5 auth
- **Priority:** P0
- **Status:** `ALREADY_CLOSED` (code)
- **Evidence:** PRs #333–#338, #350–#351 on master
- **Blocks:** no / verification still open / yes until verified

---

### 3.B REPO_CLOSABLE

#### RC-01 — FORCE RLS for ticket tiers + product_relations (+ optional translation_overrides)

- **Gate / gap:** G0 / VC-P02 / FD-07 / D32
- **Priority:** P0
- **Status:** `REPO_CLOSABLE`
- **Evidence:** migrations `0048`/`0049`/`0052` ENABLE only; live `relforcerowsecurity=false` for those three; `translation_overrides` also ENABLE-only in repo
- **Files likely:** `supabase/migrations/0064_force_rls_ticket_product_relations.sql` (number after collide resolve), `services/api/tests/rls/*`
- **Deps:** DEP-01 numbering plan
- **Acceptance:** `relforcerowsecurity=true` for the three tables; RLS matrix green
- **Verify:** SQL probe in `release-gates.md` G0; `pnpm`/pytest RLS job
- **Blocks browse-beta:** no (invite/demo OK) · **real-money:** yes · **public_launch:** yes
- **PR boundary:** `M03-FORCE-RLS` single migration PR

#### RC-02 — Migration ledger reconcile (live `0063` revoke vs repo source_key)

- **Gate / gap:** G9 / migration drift
- **Priority:** P0
- **Status:** `REPO_CLOSABLE`
- **Evidence:** live name `0063_revoke_execute_review_reply_guards` not on master; master `0063_refunds_source_key_uniq.sql`; branch `claude/convergeo-bug-audit-nu1g4b` holds revoke file
- **Files likely:** add `0063_revoke_execute_review_reply_guards.sql` (match live), renumber source_key → `0064_refunds_source_key_uniq.sql`, update any path refs/tests; **preserve SQL body of #352**
- **Deps:** none
- **Acceptance:** fresh `db reset` applies revoke then source_key; live can apply source_key as next version without double-`0063`
- **Verify:** `scripts/ci/migration-replay.sh` / CI db job
- **Blocks browse-beta:** no · **real-money:** yes (refunds correctness) · **public_launch:** yes
- **PR boundary:** `chore(db): reconcile 0063 revoke + renumber source_key 0064` — **not** a feature rewrite

#### RC-03 — n8n backup workflow JSON

- **Gate / gap:** G7 / VD-P04 / BG-5
- **Priority:** P0
- **Status:** `REPO_CLOSABLE`
- **Evidence:** `infra/n8n/backup-schedule.md` only; no `backup.json` among 19 JSONs
- **Files likely:** `infra/n8n/backup.json`, `docs/ops/n8n-workflows.md`
- **Deps:** DEP-03 import
- **Acceptance:** importable workflow producing dated backup artifact per contract
- **Verify:** n8n validate + dry execution
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** `VD-P04` alone

#### RC-04 — Server-side demo catalogue exclusion

- **Gate / gap:** G11 / VC-P06 / FD-04
- **Priority:** P1
- **Status:** `REPO_CLOSABLE`
- **Evidence:** client `apps/customer/.../demo-listing.ts` only; no demo filter in `services/api` search/catalog routers
- **Files likely:** `services/api/app/routers/search.py`, `catalog.py` (and related services), tests
- **Deps:** none
- **Acceptance:** public discovery excludes demo public_ids; verified tests
- **Verify:** `uv run pytest` catalog/search
- **Blocks browse-beta:** soft (disclosure OK) · **real-money:** no · **public_launch:** yes
- **PR boundary:** `VC-P06` API-only

#### RC-05 — E2E specs: false-success + critical-path

- **Gate / gap:** S6 / G4 / G16 / VB-P07 / VE-P07
- **Priority:** P0
- **Status:** `REPO_CLOSABLE`
- **Evidence:** only 5 specs under `e2e/specs/` — missing `checkout-false-success.spec.ts`, `critical-path.spec.ts`
- **Files likely:** `e2e/specs/*.spec.ts`, `.github/workflows/e2e.yml`
- **Deps:** LIVE-01 for green on deployed target
- **Acceptance:** pending/failed ≠ paid; COD isolated; critical path smoke
- **Verify:** `pnpm e2e` (or package script) against staging/sandbox
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** one E2E PR (two specs)

#### RC-06 — CI: make secret-scan (+ optional LH) blocking

- **Gate / gap:** G8 / G19 / VE-P04
- **Priority:** P1
- **Status:** `REPO_CLOSABLE`
- **Evidence:** `.github/workflows/ci.yml` `secret-scan` `continue-on-error: true` (~L179); `perf.yml` Lighthouse `continue-on-error: true`
- **Files likely:** `ci.yml`, `perf.yml`, `docs/ops/ci.md`
- **Deps:** FOUNDER branch-protection no-bypass
- **Acceptance:** secret-scan fails the job; LH policy decided (blocking or explicit waiver)
- **Verify:** CI on PR that would fail scan
- **Blocks browse-beta:** no · **real-money:** preferred yes · **public_launch:** yes
- **PR boundary:** CI-only PR

#### RC-07 — RLS matrix rows for newer tables

- **Gate / gap:** VC-P04 / M03
- **Priority:** P1
- **Status:** `REPO_CLOSABLE`
- **Evidence:** policies exist for `event_categories`, `product_relations`, `service_reviews`; matrix gaps called in representation report
- **Files likely:** `services/api/tests/rls/test_matrix.py`
- **Deps:** none
- **Acceptance:** `test_no_untested_tables` clean for those
- **Verify:** RLS CI job
- **Blocks browse-beta:** no · **real-money:** soft · **public_launch:** yes
- **PR boundary:** tests-only

#### RC-08 — Authenticate `uptime-alert` webhook

- **Gate / gap:** G6 / VD-P05
- **Priority:** P1
- **Status:** `REPO_CLOSABLE`
- **Evidence:** `infra/n8n/uptime-alert.json` webhook `options: {}`
- **Files likely:** that JSON + UptimeRobot shared-secret docs
- **Deps:** DEP-03 import; FOUNDER UptimeRobot
- **Acceptance:** unauthenticated POST rejected
- **Verify:** curl without secret → 401/403
- **Blocks browse-beta:** no · **real-money:** soft · **public_launch:** yes
- **PR boundary:** n8n JSON + ops note

#### RC-09 — Wire orphan UI: `report-review`, `accept-flow`

- **Gate / gap:** 00-status carried debt
- **Priority:** P2
- **Status:** `REPO_CLOSABLE`
- **Evidence:** components exist; no page importers (grep)
- **Files likely:** PDP review section; `account/jobs/[id]/page.tsx`
- **Deps:** none
- **Acceptance:** mounted + i18n keys
- **Verify:** typecheck + smoke
- **Blocks browse-beta / real-money / public_launch:** no / no / soft
- **PR boundary:** customer UI PR

#### RC-10 — De-route `zh` from public LOCALES

- **Gate / gap:** VF-P02 / NB-1
- **Priority:** P2
- **Status:** `REPO_CLOSABLE`
- **Evidence:** `packages/i18n/src/locales.ts` includes `zh`
- **Files likely:** locales + middleware + tests
- **Deps:** none
- **Acceptance:** public switcher EN/bem/nya/fr only
- **Verify:** i18n lint + route tests
- **Blocks:** no / no / soft for public_launch
- **PR boundary:** i18n-only

#### RC-11 — bem/nya namespace completion

- **Gate / gap:** G18 / VF-P01
- **Priority:** P2 / post-launch OK for invite-beta
- **Status:** `REPO_CLOSABLE` (+ human review)
- **Evidence:** ~8/17 namespaces; `PHASE1_NATIVE_REVIEW.md`
- **Files likely:** `packages/i18n/messages/{bem,nya}/*`
- **Deps:** FOUNDER native review
- **Acceptance:** purchase/legal/checkout keys complete
- **Verify:** i18n-lint
- **Blocks browse-beta:** no · **real-money:** no · **public_launch:** soft (D27)
- **PR boundary:** per-namespace PRs

#### RC-12 — Vendor default-palette → tokens (dark)

- **Gate / gap:** UI follow-up
- **Priority:** P2
- **Status:** `REPO_CLOSABLE`
- **Evidence:** ~12–14 vendor components using `neutral-*`/`emerald-*`/etc.
- **Files likely:** `apps/vendor/**`
- **Blocks:** no / no / no
- **PR boundary:** vendor polish PR

#### RC-13 — CSP nonce enforce mode

- **Gate / gap:** M15-P03 residual
- **Priority:** P2
- **Status:** `REPO_CLOSABLE`
- **Evidence:** `docs/ops/security-headers.md` report-only deferral
- **Files likely:** next configs + middleware
- **Blocks:** no / no / soft
- **PR boundary:** security headers PR

---

### 3.C DEPLOYMENT_REQUIRED

#### DEP-01 — Apply `refunds.source_key` to live (after RC-02)

- **Gate / gap:** G9 / returns
- **Priority:** P0
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** live column absent; still `refunds_order_id_active_uniq`
- **Files:** apply SQL from #352 body (as `0064` post-reconcile) — **no redesign**
- **Deps:** RC-02
- **Acceptance:** `source_key` NOT NULL + `refunds_source_key_active_uniq`; old order unique dropped
- **Verify:** SQL column/index probe
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** ops apply after RC-02 merge

#### DEP-02 — Import + activate dormant n8n fleet

- **Gate / gap:** S4 / G5 / G21 / DL-4
- **Priority:** P0
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** n8n MCP count=2; repo has release-job, order-jobs, tickets-*, event-release, lifecycle JSONs inactive live
- **Files:** `infra/n8n/*.json` (import)
- **Deps:** API internal routes + tokens; RC-03 for backup
- **Acceptance:** release + tickets-issue/release + event-release active; idempotent single-tick proof
- **Verify:** n8n execution IDs; unauthorized tick → 401/403
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** ops runbook + optional evidence doc only

#### DEP-03 — Pin + record API GHCR digest; confirm tip routes

- **Gate / gap:** DL-5 / G9 / VA-P03
- **Priority:** P0
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** digest historically NOT_AUDITABLE; money routes must match `0059`/`0062`/source_key-era code
- **Files:** host compose/env evidence note under `docs/production-readiness/…/evidence/`
- **Deps:** DEP-01 for full parity
- **Acceptance:** recorded digest; `/healthz`/`/readyz` 200; KYC + money routes present
- **Verify:** `curl` + `docker image inspect` on host
- **Blocks browse-beta:** soft · **real-money:** yes · **public_launch:** yes
- **PR boundary:** evidence-only PR after ops

#### DEP-04 — Enable Supabase Auth role hook (`0051`)

- **Gate / gap:** G0 / FD-03
- **Priority:** P0
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** `0051` applied; hook enablement still ops (vision audit / representation report)
- **Deps:** LIVE-05 role isolation re-probe
- **Acceptance:** JWT carries role consistent with `user_roles`
- **Verify:** Auth hook config + isolation suite against live
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** ops + evidence

#### DEP-05 — Enable leaked-password protection

- **Gate / gap:** G20
- **Priority:** P2
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** advisor item in vision corpus
- **Blocks:** no / no / soft
- **PR boundary:** ops checkbox

#### DEP-06 — Promote vendor (optional) / admin SHA record

- **Gate / gap:** DL-2 / G17
- **Priority:** P1
- **Status:** `DEPLOYMENT_REQUIRED`
- **Evidence:** vendor production `1d137ae` vs master `b1ea6a3` (docs-only delta); admin Access-gated
- **Acceptance:** recorded prod SHAs + honesty probes
- **Verify:** Vercel API / HTML probes
- **Blocks browse-beta:** no · **real-money:** no · **public_launch:** yes (G17)
- **PR boundary:** evidence doc

#### DEP-07 — Apply FORCE RLS migration live

- **Gate / gap:** G0
- **Priority:** P0
- **Status:** `DEPLOYMENT_REQUIRED`
- **Deps:** RC-01
- **Acceptance:** live `relforcerowsecurity=true` for ticket/product_relations
- **Verify:** G0 SQL
- **Blocks:** no / yes / yes

---

### 3.D LIVE_VERIFICATION_REQUIRED

#### LIVE-01 — S1 Sandbox MoMo → ledger

- **Gate:** S1 / G3
- **Priority:** P0
- **Status:** `BLOCKED_EXTERNAL` (F9b + API tip)
- **Evidence:** Prompt 8 `lenco-sandbox-money-drill.md` — no agent `LENCO_*`; API 502; live money rows still 0; drill A NOT RUN
- **Deps:** F9b sandbox creds; DEP-03; isolated stack
- **Acceptance:** `CHARGE_RECEIVED` + hold legs; idempotent replay
- **Verify:** VB-P01 drill + redacted Lenco dashboard
- **Blocks browse-beta:** no · **real-money:** yes · **public_launch:** yes
- **PR boundary:** evidence pack only

#### LIVE-02 — S2 Sandbox card → ledger

- **Gate:** S2 / G3
- **Priority:** P0
- **Status:** `BLOCKED_EXTERNAL` (same preflight)
- **Evidence:** Prompt 8 section B NOT RUN
- **Deps:** F9b; hosted widget; healthy sandbox API
- **Acceptance:** same as S1 for card
- **Blocks:** no / yes / yes

#### LIVE-03 — S3 Release accounting drill

- **Gate:** S3 / G3
- **Priority:** P0
- **Status:** `BLOCKED_EXTERNAL` (same + release inactive)
- **Evidence:** Prompt 8 section E NOT RUN; n8n release-job not active
- **Deps:** DEP-02 release-job; LIVE-01
- **Acceptance:** `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; escrow→0; double-tick safe
- **Verify:** release tick + SQL
- **Blocks:** no / yes / yes

#### LIVE-04 — S4 n8n release + tickets on staging/live-beta

- **Gate:** S4 / G5
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Deps:** DEP-02
- **Acceptance:** active=true; no double release/issue
- **Blocks:** no / yes / yes

#### LIVE-05 — S5 KYC lifecycle drill

- **Gate:** S5 / G12
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Evidence:** `0056` applied; `kyc_records=0`
- **Deps:** DEP-04; orphan repair FOUNDER ops
- **Acceptance:** submit→approve; privileges freeze without record
- **Blocks:** no / yes / yes

#### LIVE-06 — S6 False-success E2E

- **Gate:** S6 / G4
- **Priority:** P0
- **Status:** `BLOCKED_EXTERNAL` (Prompt 8 D NOT RUN)
- **Evidence:** `lenco-sandbox-money-drill.md` — provider pending/failed/cancelled/malformed/timeout matrix not executed
- **Deps:** RC-05; deployed target + F9b
- **Acceptance:** pending/failed ≠ paid
- **Blocks:** no / yes / yes

#### LIVE-07 — S7 UAT notes pack

- **Gate:** S7 / G16
- **Priority:** P1
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Acceptance:** 3–5 written tester journeys
- **Blocks:** no / soft / yes

#### LIVE-08 — G6 Sentry + uptime fire

- **Gate:** G6
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED` (+ FOUNDER project create)
- **Deps:** FOUNDER DSNs / UptimeRobot; RC-08
- **Acceptance:** test event ingested; uptime alert fires
- **Blocks:** no / yes / yes

#### LIVE-09 — G7 backup + ≤30-min restore

- **Gate:** G7
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Deps:** RC-03 + DEP-02 backup workflow
- **Acceptance:** dated artifact + documented restore success
- **Verify:** `restore-staging.sh` / DR runbook
- **Blocks:** no / yes / yes

#### LIVE-10 — G9 rollback drill

- **Gate:** G9 / launch-checklist §3
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Acceptance:** timed Vercel + API rollback recorded
- **Blocks:** no / yes / yes

#### LIVE-11 — Load test p95 @100cc + invariants

- **Gate:** M16-P08 / checklist §3
- **Priority:** P1
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Acceptance:** p95<500ms; zero oversell/ledger/invoice-gap
- **Blocks:** no / soft / yes

#### LIVE-12 — Search `degraded` re-probe

- **Gate:** VF-P04 / MR-B07
- **Priority:** P1
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Evidence:** 07-19 observed `degraded=true`; no proven fix
- **Deps:** embeddings cron (DEP-02)
- **Acceptance:** `/search` healthy with embeddings or documented degraded mode
- **Blocks browse-beta:** soft · **real-money:** no · **public_launch:** soft

#### LIVE-13 — Paid-ticket exactly-once + event escrow

- **Gate:** G5 / M10
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Deps:** DEP-02 tickets + event-release
- **Blocks:** no / yes / yes

#### LIVE-14 — Go/No-Go evidence pack (VE-P09)

- **Gate:** Section 0 / release-gates
- **Priority:** P0
- **Status:** `LIVE_VERIFICATION_REQUIRED`
- **Acceptance:** filled pack flips gates PASS where earned
- **Blocks:** no / yes / yes

---

### 3.E FOUNDER_REQUIRED

| ID     | Gate                          | Pri         | Status             | Evidence / action                            | Blocks browse / money / public_launch  | PR boundary     |
| ------ | ----------------------------- | ----------- | ------------------ | -------------------------------------------- | -------------------------------------- | --------------- |
| F-02   | F2 PACRA+TPIN                 | P0          | `FOUNDER_REQUIRED` | checklist unchecked                          | no / yes / yes                         | none            |
| F-03   | F3 Lenco docs confirm         | P1          | `FOUNDER_REQUIRED` | distilled exists — confirm complete          | no / soft / soft                       | none            |
| F-05   | F5 WhatsApp Cloud + templates | P0          | `FOUNDER_REQUIRED` | adapter ready; no proven WA send             | no / soft (notify) / yes               | none            |
| F-06   | F6 courier MOUs               | post-launch | `FOUNDER_REQUIRED` | post-beta OK                                 | no / no / no                           | none            |
| F-07   | F7 design HTMLs               | P2          | `FOUNDER_REQUIRED` | SOURCES: **6** missing (checklist “7” stale) | no / no / soft                         | upload only     |
| F-08   | F8 COD cap confirm            | P1          | `FOUNDER_REQUIRED` | `platform_config.cod_cap_ngwee`              | no / soft / yes                        | config          |
| F-09a  | F9a Zamtel collections        | P1          | `FOUNDER_REQUIRED` | default keep off                             | no / no if off / yes if enabling       | decision        |
| F-09b  | F9b Lenco sandbox+prod creds  | P0          | `FOUNDER_REQUIRED` | blocks LIVE-01..03                           | no / **yes** / yes                     | secrets env     |
| F-INV  | Invite cohort                 | P1          | `FOUNDER_REQUIRED` | checklist §6                                 | **yes for real beta users** / no / yes | admin UI        |
| F-SEN  | Sentry projects + DSNs        | P0          | `FOUNDER_REQUIRED` | none exist                                   | no / yes / yes                         | env             |
| F-UP   | UptimeRobot monitors          | P0          | `FOUNDER_REQUIRED` | NOT_AUDITABLE                                | no / yes / yes                         | ops             |
| F-BP   | Branch protection no-bypass   | P1          | `FOUNDER_REQUIRED` | `ci.md` process                              | no / soft / yes                        | GitHub settings |
| F-ORPH | Repair orphan KYC vendors     | P1          | `FOUNDER_REQUIRED` | FD-12                                        | no / yes / yes                         | ops SQL         |
| F-CTA  | Seller CTA env if still unset | P1          | `FOUNDER_REQUIRED` | G10 / DL-6 historically                      | soft / no / yes                        | Vercel env      |

---

### 3.F LEGAL_REQUIRED

#### L-01 — F4 / G13 counsel on escrow (NPS Act 2026)

- **Priority:** P0
- **Status:** `LEGAL_REQUIRED`
- **Evidence:** launch-checklist F4 unchecked; release-gates G13 FAIL
- **Acceptance:** written counsel sign-off artifact
- **Verify:** document attached to go/no-go pack
- **Blocks browse-beta:** no · **real-money:** **yes** · **public_launch:** **yes**
- **PR boundary:** none (legal artifact link only)

#### L-02 — Legal pages “published” go-live

- **Gate:** checklist §5
- **Priority:** P1
- **Status:** `LEGAL_REQUIRED` (+ FOUNDER publish)
- **Evidence:** routes exist; publish = go-live action
- **Blocks:** no / soft / yes

---

### 3.G DELIBERATELY_DEFERRED

| ID    | Item                                     | Decision                                        | Pri                    |
| ----- | ---------------------------------------- | ----------------------------------------------- | ---------------------- |
| DD-01 | M17 Vergeo Clips video feed              | post-launch; `docs/plan/m17-video-feed.md` only | post-launch            |
| DD-02 | Full B2B (net-terms, credit, orgs)       | D28 Phase 2                                     | post-launch            |
| DD-03 | Wallet / financing / referrals / loyalty | D1–D34 / §G                                     | post-launch            |
| DD-04 | Multi-warehouse / lots / courier API     | deferred                                        | post-launch            |
| DD-05 | Native app / airtime rails               | deferred                                        | post-launch            |
| DD-06 | PWYW / true recurrence / ticket resale   | D29                                             | post-launch            |
| DD-07 | Zamtel collections (until F9a)           | default off                                     | post-launch            |
| DD-08 | Admin multi-tier RBAC UI                 | FD-02                                           | post-launch / decision |
| DD-09 | VSDC live (seam stub OK)                 | VAT off at launch                               | post-launch            |

---

### 3.H STALE_DOCUMENTATION

| ID    | Doc claim                                                                       | Why stale                                                | Fix boundary                                   |
| ----- | ------------------------------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------- |
| SD-01 | Gap analysis: “#352 pending”; tip pre-source_key                                | #352 merged at `496819b`                                 | note in this board; optional later doc refresh |
| SD-02 | Representation report: tip `1d137ae`; #352/#353 unmerged; Supabase unverifiable | tip `b1ea6a3`; Supabase re-probed; #352/#353/#355 merged | this board supersedes                          |
| SD-03 | Gap analysis: “`0057–0062` may lag”                                             | applied live 2026-07-20                                  | this board                                     |
| SD-04 | Vision audit DL-1 categories 500 / customer `cc4a824`                           | customer prod `b1ea6a3`                                  | vision-audit age                               |
| SD-05 | Vision audit DL-3 unapplied `0051`/`0053`–`0056`                                | applied; new residual is source_key collision + FORCE    | vision-audit age                               |
| SD-06 | `00-status.md` “remaining = founder gates only”                                 | deploy/verify/ops/money drills remain                    | status refresh (separate PR)                   |
| SD-07 | `launch-checklist` F7 “7 design files”                                          | SOURCES.md: **6** missing                                | checklist wording                              |
| SD-08 | `docs/ops/ci.md` secret-scan as required while `continue-on-error`              | CI still advisory                                        | ci.md + RC-06                                  |
| SD-09 | Release-gates “`0056` unapplied” / G12 note                                     | `0056` applied; G12 still needs LIVE-05                  | release-gates refresh                          |
| SD-10 | Representation “0 gates PASS” still directionally true                          | keep; do not claim PASS without evidence packs           | n/a                                            |

_Per task scope: only this board file is added unless a link would break — no mass doc rewrites in this PR._

---

## 4. Counts by category

| Category                     | Count (board IDs) |
| ---------------------------- | ----------------- |
| `ALREADY_CLOSED`             | 9 (AC-01…09)      |
| `REPO_CLOSABLE`              | 13 (RC-01…13)     |
| `DEPLOYMENT_REQUIRED`        | 7 (DEP-01…07)     |
| `LIVE_VERIFICATION_REQUIRED` | 14 (LIVE-01…14)   |
| `FOUNDER_REQUIRED`           | 14 (F-* table)    |
| `LEGAL_REQUIRED`             | 2 (L-01…02)       |
| `DELIBERATELY_DEFERRED`      | 9 (DD-01…09)      |
| `STALE_DOCUMENTATION`        | 10 (SD-01…10)     |

---

## 5. Remaining P0 — repo vs external

### P0 repo tasks (`REPO_CLOSABLE`)

1. **RC-02** migration ledger reconcile (revoke on master + renumber source_key → 0064) — **do not reimplement source_key**
2. **RC-01** FORCE RLS migration
3. **RC-03** `backup.json`
4. **RC-05** false-success + critical-path E2E specs
5. (P1 but high leverage) RC-04 demo exclusion, RC-06 CI blocking, RC-07 matrix, RC-08 uptime auth

### P0 external (`DEPLOYMENT` + `LIVE` + `FOUNDER` + `LEGAL`)

1. **DEP-01** apply source_key to live (after RC-02)
2. **DEP-02** n8n import/activate (release, tickets, event-release, order-jobs, backup)
3. **DEP-03** pin API digest
4. **DEP-04** enable role hook
5. **DEP-07** apply FORCE RLS live
6. **LIVE-01…06, LIVE-08…10, LIVE-13…14** money/KYC/false-success/ops drills + go/no-go pack
7. **F-09b**, **F-SEN**, **F-UP**, **F-05** (notify path)
8. **L-01** counsel (G13)

---

## 6. Recommended execution order

1. **RC-02** (numbering) → **DEP-01** (apply source_key) — unblock refund correctness on live.
2. **RC-01** → **DEP-07** FORCE RLS.
3. **RC-03** → **DEP-02** n8n fleet (release/tickets/event/order + backup).
4. **DEP-03** API digest pin + route probe.
5. **F-09b** → **LIVE-01…03** sandbox money → **LIVE-04/13** automation proof.
6. **RC-05** → **LIVE-06** false-success.
7. **LIVE-05** KYC (+ F-ORPH / DEP-04).
8. **RC-03/DEP-02 backup** → **LIVE-09** restore; **LIVE-08** Sentry/uptime; **LIVE-10** rollback.
9. Start **L-01** in parallel (longest external lead).
10. Hardening wave: RC-04/06/07/08; LIVE-11/12; F-02/F-05/F-08/F-INV.
11. **LIVE-14** + Section 0 sign-off → only then real-money beta; later G10–G17 → `public_launch`.

**Safe today:** invite/demo browse with `public_launch=false`, demo disclosure, no prepaid production enablement.  
**Unsafe:** open launch or real customer MoMo/card funds.

---

## 7. Browse-beta vs real-money vs `public_launch`

| Mode                    | Blocked by                                                                   |
| ----------------------- | ---------------------------------------------------------------------------- |
| Invite browse-only beta | Mostly honesty/env (CTA, demo disclosure), invite cohort; **not** F4/F9b     |
| Real-money beta         | S1–S6, G0 FORCE RLS, G5 n8n, G6/G7/G9, F9b, L-01/G13, DEP-01 source_key live |
| `public_launch=true`    | All P0 above + G10–G13 (+ G14–G17 for open positioning)                      |

---

## 8. Assessment statements now stale (do not trust)

1. “#352 / source_key pending merge” (both July 20 reports).
2. “Migrations `0057–0062` unapplied / may lag” — **applied**; residual is **source_key** + collision.
3. “Live stuck at ≤0056” (07-19 vision audit DL-3).
4. “Customer prod `cc4a824` / categories 500” (DL-1) — prod @ `b1ea6a3`.
5. “Remaining to launch = founder gates only” (`00-status.md`).
6. “F7 = 7 missing HTML files” — **6** per SOURCES.md.
7. Representation report “Supabase not verifiable this session” — re-probed 2026-07-20.
8. Gap-analysis program step “Merge remaining money PRs — #352” — done.
9. Any claim that live `0063` is source_key — live `0063` is **revoke_execute_review_reply_guards**.
10. Treat readiness % from either report as current without this board’s live fingerprint.

---

_Board generated for execution planning. No application runtime code changed in the PR that introduces this file._
