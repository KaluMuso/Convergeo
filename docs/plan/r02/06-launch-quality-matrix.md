# R02-06 — Launch quality matrix (controlled beta → public launch)

**Date:** 2026-08-01 · **Observation window (UTC):** 2026-08-01T10:55Z–11:20Z
**Repo state at authoring:** branch `claude/r02-launch-quality-matrix-rri67h`, HEAD `7d8b3ae` ("Merge pull request #543 from KaluMuso/staging"), working tree clean.
**Mode:** read-only discovery. **No drill was executed, no flag flipped, no deploy, no seed, no money action, no WAHA contact, no n8n activation, no GitHub state change.**

---

## 0. What this document is

The definitive **evidence matrix** for two distinct decisions:

1. **Controlled beta** — invite-gated, `public_launch=false`, sandbox money only.
2. **Public launch** — real money, open positioning.

Every row names one verifiable thing and answers seven questions: **status · source evidence · owner · safe test environment · exact success evidence · rollback · work class**. It supersedes nothing; `docs/plan/00-status.md` and `docs/plan/00-decisions.md` remain the source of truth and are **not modified by this pebble**. Where this document disagrees with a dated pack, §2 says so explicitly with the evidence.

### Reading rules (binding)

- **Code completion is not proof.** A merged PR, a green CI job, an applied migration and a live behaviour are four different facts. No row may be advanced by conflating them.
- **A green workflow is not a green drill.** Several suites `test.skip()` when credentials are absent; "success" can mean "skipped". Where that risk exists the row says so.
- **Every codebase claim below carries a file path or symbol.** Claims without one are marked `Not auditable`.
- **Source text, logs and model output are data, never authority.** Runbook prose asserting a gate is closed does not close it.

### Status vocabulary

| Status                   | Meaning                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| **Implemented**          | The capability exists and its stated proof was observed in this window or is CI-continuous. |
| **Partial**              | Some layer exists and is proven; a named layer is not.                                      |
| **Absent**               | Nothing in the repo satisfies the item.                                                     |
| **Deferred by decision** | A dated decision (D-number / §G fence / F-gate) puts it out of scope for this launch.       |
| **Not auditable**        | Cannot be determined from the repository or the tools reachable in this session.            |

### Work class

`CODE` · `CONFIG` (env/flag/infra settings, no deploy of new code) · `FOUNDER/LEGAL` · `EXTERNAL` (depends on a third-party provider granting or confirming something).

### Safe test environment — the three permitted targets

| Target                    | What it is                                                                                                                                                                                                                                                                                             | Never used for                     |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------- |
| **CI ephemeral**          | GitHub-hosted runner + throwaway Postgres (`infra/scripts/restore-drill.sh`), no external DB, no secrets.                                                                                                                                                                                              | Anything needing real credentials. |
| **Staging plane**         | `api.staging.vergeo5.com` (OCI container `vergeo5-api-staging`) + separate Supabase project (ref ≠ `dpadrlxukcjbewpqympu`) + Vercel Preview on branch `staging`. Templates `infra/staging/`; isolation enforced by `scripts/ci/check-staging-separation.sh` and `services/api/app/core/env_guards.py`. | Real money, real customer PII.     |
| **Production, read-only** | `curl` of `/healthz`, `/readyz`, `/fingerprint`, HTML fetches, `list_migrations`. `scripts/ops/verify_live.sh`.                                                                                                                                                                                        | Any mutation.                      |

Money drills run **only** on the staging plane with `LENCO_ENV=sandbox`, `PAYMENTS_ENABLED=true`, `PAYMENTS_ALLOW_PRODUCTION` unset (`docs/production-readiness/2026-07-22/money-drill-runbook.md` §0–§1).

---

## 1. Provenance — what was reachable this window

| Source                               | Reachable | Method                                                                                           |
| ------------------------------------ | --------- | ------------------------------------------------------------------------------------------------ |
| Git working tree / history           | yes       | `git status`, `git log`, `git show`                                                              |
| GitHub Actions (runs + jobs + steps) | yes       | GitHub MCP `actions_list`                                                                        |
| Cloudinary account usage/plan        | yes       | Cloudinary MCP `get-usage-details` (read-only)                                                   |
| Live Supabase project                | **no**    | not queried this window — DB facts below are cited from the 2026-07-27 pack and labelled as such |
| `api.vergeo5.com` / `www             | vendor    | admin.vergeo5.com`                                                                               | **no** | not probed |
| `api.staging.vergeo5.com`            | **no**    | not probed                                                                                       |
| Lenco sandbox / production           | **no**    | credentials absent; no money action attempted                                                    |
| n8n instance                         | **no**    | not queried this window                                                                          |
| Sentry / UptimeRobot                 | **no**    | not queried this window                                                                          |

Unreachable sources become **operator verification steps**, never inferred results.

---

## 2. Corrections to stale in-repo claims (evidence-backed)

The most recent consolidated pack is `docs/production-readiness/2026-07-27/release-truth.md`. Five days of commits have landed since, and **three of its statements are now out of date**. Recording this here rather than editing that dated pack — dated packs are snapshots.

| Stale claim                                                                                       | Where                                        | Correction (2026-08-01)                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "**Restore drill** — FAILURE, 4/4 scheduled runs failed … `backup_too_small:636<10240`"           | `release-truth.md` §2.4, RG-5                | **Now green.** Runs #9 (`c2a481d`, master, 2026-07-31T06:28Z), #10 (`4866956`, staging, 07-31T07:55Z) and #11 (`5c941e3`, master, 2026-08-01T06:14Z) all `success`. Root cause fixed in `3577eea` — `infra/scripts/restore-drill.sh` now exports `BACKUP_MODE=drill` and `BACKUP_MIN_BYTES=256` for its own disposable marker-table DB, leaving `db-dump.sh`'s production floor intact.                                                                                         |
| "verification is **not blocked** on standing up a separable staging stack (VE-P08 … Wave-4 item)" | `00-decisions.md` D30; `release-truth.md` §3 | **A staging plane now exists and deploys end to end.** `deploy-staging.yml` run #9 (`fafcc08`, 2026-08-01T09:28Z) succeeded across all seven jobs including **Deploy API to OCI staging**, **Vercel Preview (staging branch)** and **Staging smoke + evidence** (steps "Health + fingerprint" and "Migration status evidence" both `success`). This upgrades the _safe test environment_ column for every money row from "improvise an isolated target" to "the staging plane". |
| "E2E (Playwright · staging) — **not run at tip**"                                                 | `release-truth.md` §2.4                      | **Runs nightly and is green:** runs #16–#21, latest #21 at `5c941e3`, 2026-08-01T05:40Z, `success`. ⚠ **This does not upgrade any money gate** — `e2e/specs/*.spec.ts` legs that need Lenco sandbox/WhatsApp/OTP credentials `test.skip()` when the env is absent (recorded at `00-status.md` Wave-18 entry), so green here is consistent with the money legs never executing.                                                                                                  |

**One regression found, not previously recorded anywhere:**

| Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Evidence                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The **staging synthetic seed is failing.** `deploy-staging.yml` run #10 (`fafcc08`, 2026-08-01T10:28Z) failed at job "Supabase migrations + checks", step **"Synthetic seed (optional)"**. Every downstream job — _Deploy API to OCI staging_, _Vercel Preview_, _Staging smoke + evidence_ — was **skipped**. In run #9 the same step was `skipped` (seed not requested) and the run passed. So: staging deploys fine **without** the seed and fails **with** it. | GitHub MCP `actions_list list_workflow_jobs` for runs `30693808415` and `30695764799`. Repair attempts already in tree: `3577eea`, `f3583bf`/`6340515` "harden staging seed connection" (`scripts/seed_staging.py`, `services/api/tests/test_seed_staging.py`). |

This matters for the matrix because **a seeded staging DB is a precondition for the money drills, the load run and the browser-led sweeps** — an unseeded staging plane has no catalogue to check out, no listing to load-test, no page to audit. It is tracked below as `LQ-D8` and is the first pebble in §6.

---

## 3. The matrix

### 3.1 Index

| ID                                                                    | Item                                                      | Status                           | Class                | Owner           |
| --------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------- | -------------------- | --------------- |
| **A — Money path (Lenco sandbox S1–S6, escrow, refund, payout, KYC)** |                                                           |                                  |                      |                 |
| LQ-A1                                                                 | S1 MoMo (MTN) collection → ledger                         | Partial                          | FOUNDER/EXTERNAL     | Founder         |
| LQ-A2                                                                 | S2 card collection → ledger                               | Partial                          | FOUNDER/EXTERNAL     | Founder         |
| LQ-A3                                                                 | S3 release accounting (commission before release)         | Partial                          | FOUNDER              | Founder         |
| LQ-A4                                                                 | S4 money n8n workflows active + authed ticks              | Partial                          | CONFIG               | Founder         |
| LQ-A5                                                                 | S5 KYC lifecycle drill                                    | Partial                          | FOUNDER              | Founder         |
| LQ-A6                                                                 | S6 false-success matrix                                   | Partial                          | FOUNDER              | Founder         |
| LQ-A7                                                                 | Webhook replay / concurrent-duplicate idempotency         | Partial                          | FOUNDER              | Founder         |
| LQ-A8                                                                 | Vendor payout transfer leg                                | Partial                          | FOUNDER/EXTERNAL     | Founder         |
| LQ-A9                                                                 | Refund lanes 1 & 2 as ledger-orchestrated payout          | Partial                          | FOUNDER              | Founder         |
| LQ-A10                                                                | F4 — counsel review of escrow under NPS Act 2026          | Absent                           | FOUNDER/LEGAL        | Founder+Counsel |
| LQ-A11                                                                | F9b — Lenco sandbox + production credentials              | Absent                           | EXTERNAL             | Founder         |
| **B — Airtel settlement**                                             |                                                           |                                  |                      |                 |
| LQ-B1                                                                 | Airtel collection rail in the drill harness               | Implemented                      | CODE                 | done            |
| LQ-B2                                                                 | Airtel settlement object evidence (settled/instant)       | Absent                           | FOUNDER/EXTERNAL     | Founder         |
| LQ-B3                                                                 | F9a — Zamtel collections confirmation                     | Absent                           | EXTERNAL             | Founder         |
| **C — Scanner / QR / OTP**                                            |                                                           |                                  |                      |                 |
| LQ-C1                                                                 | Dynamic ticket QR — 60 s rotation, single-use             | Partial                          | FOUNDER              | Founder/Ops     |
| LQ-C2                                                                 | Organiser scanner PWA — offline scan-sync                 | Partial                          | FOUNDER              | Founder/Ops     |
| LQ-C3                                                                 | Pickup QR + PIN verify                                    | Partial                          | FOUNDER              | Founder/Ops     |
| LQ-C4                                                                 | Phone-OTP auth incl. brute-force ceiling                  | Partial                          | FOUNDER/EXTERNAL     | Founder         |
| **D — API / domain / CORS / cart / search / migration**               |                                                           |                                  |                      |                 |
| LQ-D1                                                                 | Production API health + traceable `git_sha`               | Partial (**FAIL** at last probe) | CONFIG               | Founder/Ops     |
| LQ-D2                                                                 | Custom-domain frontend health (3 apps)                    | Not auditable                    | CONFIG               | Founder/Ops     |
| LQ-D3                                                                 | CORS allowlist correct on each deployed env               | Partial                          | CONFIG               | Founder/Ops     |
| LQ-D4                                                                 | Cart + guest→auth merge on a deployed surface             | Partial                          | FOUNDER              | Founder/Ops     |
| LQ-D5                                                                 | Search non-degraded on a deployed surface                 | Partial                          | CONFIG               | Founder/Ops     |
| LQ-D6                                                                 | Migration ledger parity `0072`–`0079`                     | Partial (**FAIL** on production) | CONFIG               | Founder/Ops     |
| LQ-D7                                                                 | Staging-plane isolation from production                   | Implemented                      | CODE+CONFIG          | done            |
| LQ-D8                                                                 | Staging synthetic seed                                    | **Partial — failing**            | CODE                 | Eng             |
| **E — Backup / restore / failure alerts**                             |                                                           |                                  |                      |                 |
| LQ-E1                                                                 | Self-contained restore drill (CI)                         | Implemented                      | CODE                 | done            |
| LQ-E2                                                                 | Dated live OCI dump within RPO ≤ 24 h                     | Absent                           | CONFIG               | Founder/Ops     |
| LQ-E3                                                                 | Timed restore ≤ 30 min RTO (G7)                           | Absent                           | FOUNDER              | Founder/Ops     |
| LQ-E4                                                                 | `backup.json` activated + credentials bound               | Absent                           | CONFIG               | Founder         |
| LQ-E5                                                                 | Shared failure-alert workflow + forced-error page         | Absent                           | CONFIG               | Founder         |
| **F — Observability / rollback / load**                               |                                                           |                                  |                      |                 |
| LQ-F1                                                                 | Sentry live capture across 4 targets                      | Partial                          | CONFIG+EXTERNAL      | Founder         |
| LQ-F2                                                                 | Uptime monitor + alert actually fires                     | Absent                           | CONFIG+EXTERNAL      | Founder         |
| LQ-F3                                                                 | Rollback drill (frontends + API + DB)                     | Absent                           | CONFIG               | Founder/Ops     |
| LQ-F4                                                                 | Load 100 cc, p95 < 500 ms, invariants clean               | Partial                          | FOUNDER              | Founder/Ops     |
| **G — Cloudinary Clips cost guard**                                   |                                                           |                                  |                      |                 |
| LQ-G1                                                                 | F-V4 plan + credit headroom                               | **Partial — new evidence**       | EXTERNAL             | Founder         |
| LQ-G2                                                                 | Kill-switch drill (`clip-cost-runbook.md` §4)             | Absent                           | FOUNDER              | Founder         |
| LQ-G3                                                                 | Clips dark-ship posture (flags + schema)                  | Implemented                      | CODE                 | done            |
| LQ-G4                                                                 | Monthly spend reconciliation ours ↔ Cloudinary            | Absent                           | FOUNDER              | Founder         |
| **H — WAHA private-pilot prerequisites (nothing enabled)**            |                                                           |                                  |                      |                 |
| LQ-H1                                                                 | R1 pre-flight (migrations, flag row, allowlist, secrets)  | Absent                           | CONFIG               | Founder         |
| LQ-H2                                                                 | NB-7 three-way number separation                          | Absent                           | FOUNDER              | Founder         |
| LQ-H3                                                                 | NB-8 host / compartment isolation                         | Absent                           | CONFIG               | Founder         |
| LQ-H4                                                                 | Vendor consent enrolment + disenrolment                   | Absent                           | FOUNDER/LEGAL        | Founder         |
| LQ-H5                                                                 | Live drill dispositions + kill-switch rehearsal           | Absent                           | FOUNDER              | Founder         |
| LQ-H6                                                                 | Retention sweep + workflows imported **inactive**         | Absent                           | CONFIG               | Founder         |
| **I — SEO**                                                           |                                                           |                                  |                      |                 |
| LQ-I1                                                                 | `robots.txt` correct on the live host                     | Partial                          | CODE (done) + verify | Founder/Ops     |
| LQ-I2                                                                 | `sitemap.xml` + shards serve live and are fresh           | Partial                          | CODE (done) + verify | Founder/Ops     |
| LQ-I3                                                                 | Titles / meta descriptions per indexable route            | Partial                          | CODE                 | Eng             |
| LQ-I4                                                                 | Canonical + hreflang alternates                           | Partial                          | CODE (done) + verify | Founder/Ops     |
| LQ-I5                                                                 | Structured data validates in Google Rich Results          | Partial                          | EXTERNAL             | Founder/Ops     |
| LQ-I6                                                                 | Indexing posture while `public_launch=false`              | **Partial — open question**      | CODE+CONFIG          | Founder         |
| **J — Vernacular + copy**                                             |                                                           |                                  |                      |                 |
| LQ-J1                                                                 | Bemba coverage                                            | Partial (58.7 %)                 | CODE                 | Eng             |
| LQ-J2                                                                 | Nyanja coverage                                           | Partial (58.7 %)                 | CODE                 | Eng             |
| LQ-J3                                                                 | Human review of vernacular strings                        | Absent                           | FOUNDER              | Founder         |
| LQ-J4                                                                 | Professional EN copy pass (marketing/legal/transactional) | Absent                           | FOUNDER              | Founder         |
| **K — Browser-led verification**                                      |                                                           |                                  |                      |                 |
| LQ-K1                                                                 | Accessibility on a deployed surface                       | Partial                          | FOUNDER/Ops          | Founder/Ops     |
| LQ-K2                                                                 | Lighthouse mobile Perf/SEO/A11y on deployed URL           | Partial                          | FOUNDER/Ops          | Founder/Ops     |
| LQ-K3                                                                 | 360 px one-handed responsive sweep                        | Absent                           | FOUNDER/Ops          | Founder/Ops     |
| LQ-K4                                                                 | Fast-3G LCP ≤ 2.5 s on the deployed surface               | Partial                          | FOUNDER/Ops          | Founder/Ops     |

---

### 3.2 Row detail

Each card: **Source evidence** (what exists and where) · **Safe test environment** · **Exact success evidence** (what must be recorded, to what precision) · **Rollback**.

---

#### A — Money path

**LQ-A1 · S1 MoMo (MTN) collection → ledger** — _Partial · FOUNDER/EXTERNAL_

- **Source evidence.** Harness `scripts/drills/lenco_sandbox_money_drill.py` (dry-run and live modes); runbook `docs/production-readiness/2026-07-22/money-drill-runbook.md` §2; contract `docs/ops/lenco/lenco-api-distilled.md`; invariants `scripts/db/ledger-invariants.sql`. Code proven by unit/mock tests only (`services/api/tests/test_ledger.py`, `test_webhooks.py`). **Live counter-evidence:** `payments`, `orders`, `ledger_transactions` all `0` on production (`release-truth.md` §2.1, verified 2026-07-27).
- **Safe test environment.** Staging plane, `LENCO_ENV=sandbox`, `PAYMENTS_ENABLED=true`, `PAYMENTS_ALLOW_PRODUCTION` unset. Sandbox MTN success number `0961111111`.
- **Exact success evidence.** A redacted drill report JSON with `verdict=PASS` and `ledger_imbalance_ngwee=0`, plus the four SQL assertions from the runbook §2: exactly one `payments` row at `status='success'`; `charge_received=1` and `escrow_hold=1` in `ledger_transactions` for the order; **zero** rows from the per-`transaction_id` `sum(amount_ngwee) <> 0` query; escrow hold **equal to the order gross in integer ngwee**. Plus the pre-callback observation that `GET /payments/status` read `pending`, **not** paid.
- **Rollback.** None needed — sandbox funds. If the drill leaves broken state: `PAYMENTS_ENABLED=false` on the staging API, restore the staging DB from its own dump. Production is untouched by construction (the staging isolation guard refuses a production Supabase ref).

**LQ-A2 · S2 card collection → ledger** — _Partial · FOUNDER/EXTERNAL_

- **Source evidence.** `services/api/tests/test_payments_card.py`; hosted-widget-only constraint (D-stack, no direct card API — PCI); `NEXT_PUBLIC_LENCO_PUBLIC_KEY` required on the Vercel customer project (`money-drill-runbook.md` §1). Sandbox PANs listed in `lenco-api-distilled.md`.
- **Safe test environment.** Staging plane + Vercel Preview with the **sandbox** public key.
- **Exact success evidence.** Same ledger assertions as LQ-A1, **plus** proof that fulfilment happens only after server-side verification: a spoofed widget return must produce hold + alert and **no** confirmation (`test_payments_card.py` asserts the code path; the drill must show it on a live sandbox round trip).
- **Rollback.** As LQ-A1.

**LQ-A3 · S3 release accounting** — _Partial · FOUNDER_

- **Source evidence.** `money-drill-runbook.md` §5; internal ticks `POST /internal/order-jobs/auto-confirm`, `/auto-release`, `/internal/release-job/tick`; `services/api/tests/test_release.py`, `test_order_confirmation.py`.
- **Safe test environment.** Staging plane, ticks driven by hand with `INTERNAL_ORDER_JOBS_TOKEN` / `INTERNAL_RELEASE_JOB_TOKEN`.
- **Exact success evidence.** `commission_capture` posted **before or with** `release_to_vendor`, each exactly once; escrow remaining balance correct to the ngwee; a **second** release run posts **nothing** (idempotent); all postings zero-sum. Record the full ngwee posting table.
- **Rollback.** Sandbox only; restore staging DB if state is unusable.

**LQ-A4 · S4 money n8n workflows active with authenticated ticks** — _Partial · CONFIG_

- **Source evidence.** `money-drill-runbook.md` §7 names the workflow `Vergeo5 — payment reconciliation crons` (`C1MpTNjrfLACMG3f`) and the two distinct credentials (Reconciliation Token `wHBamWZu96ONsPts`, Payment Sweeper Token `2YIzCrGVKzsl14F6`) checking **different** env tokens (`INTERNAL_RECONCILIATION_TOKEN`, `INTERNAL_PAYMENT_SWEEPER_TOKEN`). Registry `docs/ops/n8n-workflows.md`, drift-tested by `services/api/tests/test_n8n_registry.py`.
- **Safe test environment.** Staging n8n (`n8n.staging.vergeo5.com`, per `infra/ENVIRONMENTS.md`) pointed at the staging API. **Activate only after LQ-A1 and LQ-A3 pass.**
- **Exact success evidence.** An unauthorised tick returns **401/403**; an authorised tick succeeds; a **deliberately forced mismatch** is detected and alerted **without destructive auto-correct**; no double release and no double ticket issue.
- **Rollback.** `unpublish_workflow` (or UI → inactive); confirm `search_workflows` shows `active: false`; re-import the last-good JSON from `infra/n8n/` at a known SHA with credential IDs scrubbed to `REPLACE_WITH_CREDENTIAL_ID`.

**LQ-A5 · S5 KYC lifecycle drill** — _Partial · FOUNDER_

- **Source evidence.** `services/api/tests/test_admin_kyc.py`, `test_kyc_caps.py`, `test_kyc_archetype.py`; migration `0056` applied on production; **`kyc_records = 0` live** (`release-truth.md` §2.1). Tier model D9 (T1 NRC+selfie+MoMo name match; T2 PACRA+TPIN; T3 invited).
- **Safe test environment.** Staging plane with throwaway vendor identities and **synthetic documents only** — never a real NRC.
- **Exact success evidence.** `submit → under_review → approve` observed with each transition present in `audit_log` (actor, before, after); caps enforced **server-side** after approval (a T1 vendor rejected at listing 31 and at an order over K500 within the first five orders); an **orphan report** showing zero KYC records without a vendor and zero vendors claiming a tier without a record.
- **Rollback.** Delete the throwaway identities from staging; production untouched.

**LQ-A6 · S6 false-success matrix** — _Partial · FOUNDER_

- **Source evidence.** `money-drill-runbook.md` §3 with the three sandbox failure numbers (`0962222222` insufficient funds, `0966666666` timeout, Airtel `0972222222` wrong PIN); `e2e/specs/checkout-false-success.spec.ts`; client branches on `data.status` not HTTP 200 (`services/api/app/services/payments/lenco/client.py`).
- **Safe test environment.** Staging plane, sandbox failure numbers.
- **Exact success evidence.** For **each** failure number: order never reads paid or completed; **zero** ledger transactions; UI shows a failure state, not a success. Plus the COD path (≤ K500) never claims MoMo success. A screenshot per case plus the SQL count is the artifact.
- **Rollback.** None; nothing is created on failure by design — that is the assertion.

**LQ-A7 · Webhook replay + concurrent-duplicate idempotency** — _Partial · FOUNDER_

- **Source evidence.** `money-drill-runbook.md` §4; idempotency key `event:data.id` in `services/api/app/routers/webhooks_lenco.py`; `services/api/tests/test_webhooks.py`. Signature = HMAC-**SHA512** of the raw body keyed by SHA256-hex of the API token.
- **Safe test environment.** Staging plane; re-POST the identical signed body, then two concurrently.
- **Exact success evidence.** Still exactly one `payments` success row, one `charge_received`, one `escrow_hold`; no new settlement rows. **Also** record that a forged signature returns 401 and stores nothing.
- **Rollback.** None.

**LQ-A8 · Vendor payout transfer leg** — _Partial · FOUNDER/EXTERNAL_

- **Source evidence.** `money-drill-runbook.md` §6 (`POST /internal/payouts/retry-tick`); `services/api/tests/test_payouts.py` (per-vendor lock, reserved `processing` rows, name-mismatch → held, retry re-queries before re-send); fixtures `scripts/ops/staging-money-drill-fixtures.sql` prepare `payout_msisdn`/`payout_rail`.
- **Safe test environment.** Staging plane, sandbox `LENCO_ACCOUNT_ID`.
- **Exact success evidence.** A `payouts` row traversing `pending → processing → success` against the sandbox transfer; `GET /vendor/payouts` balances reflect the release; **integer ngwee end to end, no float anywhere** in the recorded amounts; a `/resolve` name mismatch produces **held, never sent**.
- **Rollback.** Sandbox transfer — no real money. Set `PAYMENTS_ENABLED=false` to stop the sweeper.

**LQ-A9 · Refund lanes 1 & 2** — _Partial · FOUNDER_

- **Source evidence.** D17 two-lane policy; refunds are **ledger-orchestrated payouts** because Lenco exposes no refunds API (`lenco-api-distilled.md`); refund-aware sweeper closed the M08-P10 debt (`00-status.md`, commits `a740148`, `e0fd185`); `services/api/tests/test_refund_execute.py`. Drill harness carries a refund-as-payout leg (`run_release_refund_live` in `scripts/drills/lenco_sandbox_money_drill.py`).
- **Safe test environment.** Staging plane, sandbox.
- **Exact success evidence.** Lane 1 (faulty): full refund **including delivery** from escrow, ledger zero-sum, refund payout row reaches `success`. Lane 2 (change-of-mind): refund equals item price − outbound delivery − return transport − restocking fee at the configured bps, **recomputed independently and matched to the ngwee**. Post-release refund shows a `CLAWBACK` against the vendor's next payout.
- **Rollback.** Sandbox only.

**LQ-A10 · F4 — counsel review of the escrow flow under NPS Act 2026** — _Absent · FOUNDER/LEGAL_

- **Source evidence.** D14 and D30 both make this a **pre-real-money gate**, not a build blocker. Brief prepared: `docs/ops/f4-escrow-legal-review-brief.md`. Regulatory context: `docs/plan/research/payments-compliance-zambia-2026-07.md` — no published threshold exempts a marketplace from PSP licensing if it holds vendor funds; riding a BoZ-licensed aggregator is the standard compliant route. **No counsel artifact exists in the repo.**
- **Safe test environment.** N/A — a written legal opinion.
- **Exact success evidence.** A dated, signed written opinion from Zambian counsel addressing: (a) whether the Lenco-held-funds + platform-ledger-of-record structure requires a PSP licence for Vergeo5 under the National Payment System Act 2026; (b) any conditions or disclosures required; (c) the refund/clawback mechanics. Filed with its date and author.
- **Rollback.** N/A. If the opinion is adverse, `public_launch` stays `false` and real money stays off — that is the control.

**LQ-A11 · F9b — Lenco sandbox + production credentials** — _Absent · EXTERNAL_

- **Source evidence.** `docs/ops/launch-gates-execution.md` §1 lists exactly what is needed (`LENCO_API_TOKEN`, `LENCO_ACCOUNT_ID`, `NEXT_PUBLIC_LENCO_PUBLIC_KEY`) and where they go. Open since 2026-07-06 (D-list F9). It gates **every** row in section A.
- **Safe test environment.** Sandbox credentials on the staging API host's secret store **only**. Never in the repo, never in a message, never on the production host during a drill.
- **Exact success evidence.** A drill run reaching `verdict=PASS` — the credentials are proven by the drill, not by their presence.
- **Rollback.** Rotate the token with Lenco support; rotating it also rotates the webhook signing key (key = SHA256-hex of the token), so re-register the webhook after rotation.

---

#### B — Airtel settlement

**LQ-B1 · Airtel collection rail in the drill harness** — _Implemented · CODE_

- **Source evidence.** Commit `9a7cec0` (cherry-pick of `51128a1`) "fix(drills): support Airtel sandbox settlements". `scripts/drills/lenco_sandbox_money_drill.py` now carries `SANDBOX_MOMO_SUCCESS_BY_RAIL = {"mtn": "0961111111", "airtel": "0971111111"}`, a `momo_rail` config field defaulting to `mtn`, a validator that adds the blocker `"DRILL_MOMO_RAIL must be 'mtn' or 'airtel'"` for any other rail, and rail-parameterised collection **and** refund calls (`"rail": self.config.momo_rail`). Report records `entities.momo_rail`. Tests: `services/api/tests/test_lenco_sandbox_money_drill.py` (+84 lines in that commit). Runbook section "Airtel collection evidence" added to `docs/ops/lenco/sandbox-money-drill.md`.
- **Safe test environment.** N/A — this row is code, and the code is present and tested.
- **Exact success evidence.** Already met: the tests are in CI and the constant/validator/parameterisation are readable at the paths above.
- **Rollback.** Revert `9a7cec0`; default reverts to MTN-only.

**LQ-B2 · Airtel settlement object evidence** — _Absent · FOUNDER/EXTERNAL_

- **Source evidence.** The Lenco contract exposes `settlementStatus: pending→settled` and `settlement{amountSettled, type: instant|next-day, accountId}` on a successful collection, plus `GET /settlements` (`lenco-api-distilled.md` §"Accounts / settlement / ledger"). **Open question F9f: the default settlement type for our account per rail is unconfirmed.** No Airtel settlement observation exists in the repo.
- **Safe test environment.** Staging plane, `DRILL_MOMO_RAIL=airtel`, `DRILL_MOMO_NUMBER=0971111111`, with a **fresh cart, checkout group and order** — the runbook explicitly forbids retrying the MTN order.
- **Exact success evidence.** Two redacted drill reports side by side (`entities.momo_rail = mtn` and `= airtel`), each showing the collection reaching `successful` and its `settlementStatus` progressing to `settled` with the observed `settlement.type`. Record the observed type per rail — that is the answer to F9f and it feeds the D5 payout promise ("paid out in minutes on mobile money — always within 48 hours").
- **Rollback.** Sandbox only.

**LQ-B3 · F9a — Zamtel collections** — _Absent · EXTERNAL_

- **Source evidence.** `lenco-api-distilled.md`: collections enum is `airtel|mtn` **only**; the payout enum includes `zamtel`. Doc 1's widget prose mentions Zamtel, Doc 2's API enum does not. Until Lenco confirms, checkout treats Zamtel as unsupported for direct push (`zamtel_collections=false`, verified live 2026-07-27) while Zamtel **payouts** are fine.
- **Safe test environment.** N/A — a written answer from Lenco support.
- **Exact success evidence.** A written confirmation from Lenco naming the exact collections operator value for Zamtel, then a staging sandbox collection on that rail reaching `successful`. Only then may `zamtel_collections` be flipped.
- **Rollback.** `zamtel_collections=false` — a config flag, no deploy, and the checkout UI already hides the rail when it is false.

---

#### C — Scanner / QR / OTP

**LQ-C1 · Dynamic ticket QR — 60 s rotation, single use** — _Partial · FOUNDER_

- **Source evidence.** `services/api/app/services/tickets/qr.py`: `WINDOW_SECONDS = 60`, `MAX_HORIZON_WINDOWS = 60`, `window_code()` = truncated HMAC-SHA256 over the window index, PIN hashed with PBKDF2 (`hash_pin`), `issue_horizon()` for offline pre-issue. Verify path `services/api/app/routers/ticket_verify.py`; tests `test_ticket_verify.py`, `test_ticket_scan_sync.py`.
- **Safe test environment.** Staging plane + a real phone. Requires LQ-D8 (seeded staging) for a sellable event.
- **Exact success evidence.** A screenshot of a QR taken at T, presented at **T + 90 s**, **rejected**. The same live QR scanned twice → **accepted once, rejected once**, with the rejection reason recorded. Both observed on a real device against staging, not in a unit test.
- **Rollback.** N/A (read path). If verification misbehaves at an event, the PIN path is the documented fallback.

**LQ-C2 · Organiser scanner PWA — offline scan-sync** — _Partial · FOUNDER_

- **Source evidence.** `services/api/app/routers/ticket_scan_sync.py`; horizon issuance in `qr.py`; PWA service worker `apps/customer/sw.ts` (checkout/cart/payment/auth are `NetworkOnly` by design — see `00-status.md` M16-P02); `e2e/specs/event-ticket.spec.ts`.
- **Safe test environment.** Staging plane, device in **airplane mode** after loading the scanner.
- **Exact success evidence.** N scans taken fully offline; on reconnect the sync posts all N; the server accepts each ticket **exactly once** including a deliberately duplicated offline scan of the same ticket from two devices. Record the sync response and the resulting ticket states.
- **Rollback.** N/A.

**LQ-C3 · Pickup QR + PIN verify** — _Partial · FOUNDER_

- **Source evidence.** `services/api/app/services/pickup/{tokens,issue,verify}.py`; router `services/api/app/routers/pickup_verify.py`.
- **Safe test environment.** Staging plane with a drill order in a pickup-eligible state.
- **Exact success evidence.** Single-use enforced (second presentation rejected); PIN fallback works when the camera fails; the order transitions through the **guarded** state function with an `audit_log` row — never a raw status UPDATE (CLAUDE.md convention 4).
- **Rollback.** N/A.

**LQ-C4 · Phone-OTP auth incl. brute-force ceiling** — _Partial · FOUNDER/EXTERNAL_

- **Source evidence.** UI `apps/customer/app/[locale]/(auth)/_components/{phone-form,otp-form,auth-utils}.tsx`; guard `services/api/app/routers/auth_guard.py` with `"POST /auth/guard/otp-quota": SENSITIVE_WRITE` in `services/api/app/core/ratelimit_policies.py`; tests `test_ratelimit.py`, `test_identity.py`; `e2e/specs/auth-otp.spec.ts` — **env-gated, skips without credentials.**
- **Safe test environment.** Staging plane with a **test** phone number. Real SMS/WhatsApp delivery depends on F5 (Meta) and the Africa's Talking fallback.
- **Exact success evidence.** A real OTP delivered to a real handset and redeemed; then N+1 wrong codes producing a **429 or lockout**, with the exact ceiling and window recorded. Delivery-channel fallback (WhatsApp → SMS) observed within the ≤ 2 min target.
- **Rollback.** N/A. If OTP delivery fails at beta, the invite gate keeps the cohort small enough to hand-recover.

---

#### D — API / domain / CORS / cart / search / migration

**LQ-D1 · Production API health + traceable `git_sha`** — _Partial, FAIL at last probe · CONFIG_

- **Source evidence.** Last in-repo probe `docs/production-readiness/2026-07-23/live-probe-gap-report.md`: `/healthz` 200 but **`GIT_SHA=unknown`** → G9 FAIL. `release-truth.md` §2.3 records the API host is updated by a **manual** `docker pull` (`infra/redeploy-api.sh`), so a green GHCR build is **not** evidence of a deploy. `git_sha` is a first-class setting (`services/api/app/settings.py`, `git_sha: str = Field(alias="GIT_SHA", default="")`) exposed on `/fingerprint`.
- **Safe test environment.** Production, **read-only** (`scripts/ops/verify_live.sh`).
- **Exact success evidence.** `curl https://api.vergeo5.com/fingerprint` returning `env`, a **non-`unknown` `git_sha` matching the intended release commit**, and the expected `supabase_project_ref`. An untraceable deploy is a blocker in its own right: you cannot roll back to a version you cannot name.
- **Rollback.** `infra/redeploy-api.sh <previous-sha>` against the immutable GHCR SHA tag. This is exactly why `git_sha` must not be `unknown`.

**LQ-D2 · Custom-domain frontend health (3 apps)** — _Not auditable · CONFIG_

- **Source evidence.** Vercel reported all three projects **READY** at master tip on 2026-07-27 (`release-truth.md` §2.2), but the same document states plainly that **READY ≠ the custom domain serving 200**. Health routes exist per app at `/<locale>/health` (`AGENTS.md`). Prober: `scripts/ops/probe-frontends.sh`.
- **Safe test environment.** Production, read-only.
- **Exact success evidence.** HTTP 200 from `https://www.vergeo5.com/en/health`, `https://vendor.vergeo5.com/en/health`, and an **Access challenge (302/401), not a 200,** from `https://admin.vergeo5.com/en/health` — admin serving 200 unauthenticated is a failure, not a pass (D20/D33: separate origin behind Cloudflare Access).
- **Rollback.** Vercel: promote the previous production deployment by `dpl_` id.

**LQ-D3 · CORS allowlist correct per environment** — _Partial · CONFIG_

- **Source evidence.** `services/api/app/settings.py` — `cors_origins` (alias `CORS_ORIGINS`) with a `model_validator` that raises `"CORS_ORIGINS must include at least one origin"` and `"CORS_ORIGINS cannot include '*' outside development"`; applied at `services/api/app/main.py:48` via `CORSMiddleware(allow_origins=settings.cors_origin_list)`. The **guard is implemented and cannot be bypassed silently** — the process refuses to start. What is unverified is the **actual value** on each deployed host.
- **Safe test environment.** Production and staging, read-only: a cross-origin preflight from an allowed origin and from a disallowed one.
- **Exact success evidence.** `OPTIONS` from `https://www.vergeo5.com` returns the origin in `Access-Control-Allow-Origin`; `OPTIONS` from an arbitrary origin does **not**; no `*` in any response outside development. Record the observed header per environment.
- **Rollback.** Edit `CORS_ORIGINS` in the host env and restart the container — config only.

**LQ-D4 · Cart + guest→auth merge on a deployed surface** — _Partial · FOUNDER_

- **Source evidence.** `services/api/tests/test_cart.py` (guest→auth merge), `test_order_create_concurrency.py` (oversell race), `test_reservations.py` (expiry restock). Browser-side cart calls use `NEXT_PUBLIC_API_BASE_URL`; `infra/ENVIRONMENTS.md` warns that if it is blank, **client cart/wishlist calls silently hit `localhost:8000`** — a real, previously-observed failure mode.
- **Safe test environment.** Staging plane (needs LQ-D8 seed).
- **Exact success evidence.** In a real browser: add to cart as a guest → sign in → the cart is **preserved with the same line items and quantities**; a second tab cannot oversell the last unit; a reservation expiring restocks. Plus a network-tab check that no request went to `localhost`.
- **Rollback.** N/A (read/verify).

**LQ-D5 · Search non-degraded on a deployed surface** — _Partial · CONFIG_

- **Source evidence.** `services/api/app/services/search/__init__.py` carries an explicit `degraded: bool` on the result, a `search_degraded` log event, and reason codes `vector_rpc_fallback` / embedding-failure. `scripts/ops/verify_live.sh` has a `check_live12_search` probe and treats a degraded semantic lane as a **warning**, not a G1 failure. Prior incident: `docs/production-readiness/2026-07-20/search-degraded-probe.md`. `infra/ENVIRONMENTS.md` names the root cause — a blank `SUPABASE_DB_URL` falls back to `127.0.0.1:54322`, making every direct-DB call 500 and search `degraded=true`.
- **Safe test environment.** Production and staging, read-only.
- **Exact success evidence.** A search response with `degraded=false` and non-empty hits for a seed term, on **both** environments, together with a keyword-only query and a semantic-only query each returning sensible results (RRF fusion actually fusing, not silently keyword-only).
- **Rollback.** Set `SUPABASE_DB_URL` correctly (session pooler, port 5432 not 6543) and restart — config only.

**LQ-D6 · Migration ledger parity `0072`–`0079`** — _Partial, FAIL on production · CONFIG_

- **Source evidence.** Repo has **79** migration files, tip `0079_clip_cost_guard.sql` (`ls supabase/migrations`). Production ledger tip was `0071_vendor_listing_compare_at` on 2026-07-27, i.e. **8 behind** (`release-truth.md` §2.1, VERIFIED). Dependency order verified file-by-file in `release-truth.md` §1.1: `0072 → 0079` in order is dependency-safe, no file references a later-numbered object. Staging applies migrations automatically — `deploy-staging.yml` job "Supabase migrations + checks" step "Push migrations from blank/current staging DB" `success` on run #9.
- **Safe test environment.** Staging first (already automated), production **only after a dated backup** (LQ-E2).
- **Exact success evidence.** `list_migrations` on the target returns tip `0079`; `to_regclass` is non-null for `video_clips`, `clip_comments`, `clip_spend_monthly`, `clip_weekly_caps`, `intake_sessions`, `intake_deep_links`; and the three flag rows `clips`, `clips_comments`, `waha_vendor_intake` **exist and read `false`**. Note the precise wording: today the checklist line "confirm the row is false" **cannot** be ticked because the row does not exist; after apply it becomes "confirm the row exists **and** is false".
- **Rollback.** Restore from the pre-migration dump (LQ-E2/E3). Migrations are additive-only post-M03 (CLAUDE.md convention 6), so the practical risk is low — but the dump is the control, not the convention.

**LQ-D7 · Staging-plane isolation from production** — _Implemented · CODE+CONFIG_

- **Source evidence.** `.github/workflows/deploy-staging.yml` pins `PROD_SUPABASE_PROJECT_REF: dpadrlxukcjbewpqympu` and `PROD_API_HOST: api.vergeo5.com` and runs a dedicated **Environment separation** job whose steps are "Refuse missing staging identifiers", "Compare staging identifiers against production", "Hard-fail on production Supabase ref or API host literals" — all `success` on runs #9 and #10. A terminal **"Guard — no production promotion"** job affirms staging-only scope. Server-side the same invariant is enforced at process start: `services/api/app/settings.py` calls `assert_staging_supabase_isolated`, `assert_staging_api_host_isolated` and `require_sandbox_payments` from `app/core/env_guards.py` — a staging API pointed at production **refuses to boot**. Supporting: `infra/staging/forbidden-production-identifiers.env`, `scripts/ci/check-staging-separation.sh`, `scripts/ci/test-staging-guards.sh`.
- **Safe test environment.** N/A — this **is** the safe test environment.
- **Exact success evidence.** Met. Re-assert on each deploy via the Environment separation job.
- **Rollback.** N/A.

**LQ-D8 · Staging synthetic seed** — _Partial, currently failing · CODE_

- **Source evidence.** `scripts/seed_staging.py` (+99 lines across `3577eea`, `f3583bf`, `6340515`), tests `services/api/tests/test_seed_staging.py` (+90 lines). **Failing in CI:** `deploy-staging.yml` run #10 (`fafcc08`, 2026-08-01T10:28Z) — job "Supabase migrations + checks", step "Synthetic seed (optional)" `failure`; downstream _Deploy API to OCI staging_, _Vercel Preview_, _Staging smoke + evidence_ all **skipped**. Run #9 passed with the same step `skipped`.
- **Safe test environment.** CI + staging (already wired via the `seed_synthetic` workflow input).
- **Exact success evidence.** One `deploy-staging` run with `seed_synthetic=true` completing **all seven jobs green**, with the seed producing a countable catalogue: N `stg-rv-*` listings visible via the staging search endpoint with `degraded=false`.
- **Rollback.** The seed writes only `stg-rv-*`-prefixed rows to the staging project; delete by prefix. Never run against production.

---

#### E — Backup / restore / failure alerts

**LQ-E1 · Self-contained restore drill (CI)** — _Implemented · CODE_

- **Source evidence.** `.github/workflows/restore-drill.yml` (nightly `30 3 * * *` + `workflow_dispatch`, deliberately **not** a PR gate) running `infra/scripts/restore-drill.sh` — seed → dump → wipe → restore → assert on a throwaway Postgres. **Green:** runs #9 (`c2a481d`), #10 (`4866956`), #11 (`5c941e3`, 2026-08-01T06:14Z) all `success`, after four consecutive failures (#4–#8) on `backup_too_small`. Fix `3577eea`.
- **Safe test environment.** CI ephemeral — no external DB, no secrets, production untouched.
- **Exact success evidence.** Already met and continuously re-proven nightly. Watch for regression.
- **Rollback.** N/A.

**LQ-E2 · Dated live OCI dump within RPO ≤ 24 h** — _Absent · CONFIG_

- **Source evidence.** `infra/scripts/db-dump.sh` writes `db/vergeo5-<ts>.sql.gz` to OCI Object Storage; retention 14 days (`BACKUP_RETENTION_DAYS`, D21); verifier `scripts/ops/backup_drill.sh --verify-oci`. **The backup workflow is inactive** (`release-truth.md` §2.5: _Vergeo5 — Database Backup_ inactive), so no scheduled dated dump is being produced.
- **Safe test environment.** OCI host, production DB **read-only** (`pg_dump` reads).
- **Exact success evidence.** A dated object name + byte size + sha256 **prefix** recorded, with the object's age **< 24 h** at the moment of recording. Never paste the DSN or the full checksum path.
- **Rollback.** N/A (a dump is additive). If the bucket fills, prune per `BACKUP_RETENTION_DAYS`.

**LQ-E3 · Timed restore ≤ 30 min RTO (G7)** — _Absent · FOUNDER_

- **Source evidence.** `docs/ops/drill-log.md` holds one **LOCAL** drill (2026-07-12, PASS, ~2 s against a 420 KB local schema) and states in terms that local timings are **not** the RTO measurement. The live section is headed "**LIVE STAGING DRILL — founder-gated (deferred)**" with an **empty** entry line. `docs/ops/n8n-backup-and-alerts.md` §8 is explicit: "Run a **timed restore** … **this**, not the import, flips **G7 → PASS**."
- **Safe test environment.** Staging plane, restoring into a **scratch** DB. `scripts/ops/restore-staging.sh` refuses `postgres` as a target and refuses a source identical to the target — both guards evidenced in `drill-log.md` §3.
- **Exact success evidence.** A new dated `drill-log.md` entry with: `DRILL START`/`DRILL END` UTC stamps and **elapsed minutes ≤ 30**; dump size; restore duration; the smoke output (core tables present, seed tables non-empty, migration ledger latest == the repo's latest, currently `0079`); and the source dump object name + age proving RPO ≤ 24 h.
- **Rollback.** The target is a scratch DB that the script drops and recreates; nothing to roll back. Production is never a target — the guard enforces it.

**LQ-E4 · `backup.json` activated with credentials bound** — _Absent · CONFIG_

- **Source evidence.** `infra/n8n/backup.json` ships `active: false` (live id `OAdOD4kmIbSNehkJ`); review card and the **unchecked, founder-owned** activation list in `docs/ops/n8n-backup-and-alerts.md` §8. Credential IDs ship as `REPLACE_WITH_CREDENTIAL_ID`; secrets are `$env` references only, enforced by `scripts/ci/validate-n8n-no-plaintext-secrets.sh` and `scripts/ci/validate-backup-workflow.sh`. The doc contains a standing instruction that **automation must never self-activate these** — honoured: nothing was activated by this pebble.
- **Safe test environment.** Staging n8n first, then production n8n.
- **Exact success evidence.** Workflow `active: true`; the manual break-glass drill (`POST /webhook/backup-manual` with `X-Backup-Secret`) produces a dated object; timezone set to **Africa/Lusaka** and Error Workflow linked to the shared handler (both must be set in the Settings panel — the SDK import cannot set them); OCI bucket confirmed **server-side encrypted with no public access**.
- **Rollback.** `unpublish_workflow`; re-import the last-good JSON at a known SHA with credential IDs scrubbed. Do **not** rotate `N8N_ENCRYPTION_KEY` without a credential-migration plan — it invalidates every stored credential.

**LQ-E5 · Shared failure-alert workflow + forced-error page** — _Absent · CONFIG_

- **Source evidence.** `infra/n8n/money-workflow-error-alert.json`, live scaffold `LVuHqWgT1tqjYOtc` created **WhatsApp-less** — the committed JSON is authoritative and **includes** the WhatsApp node plus the dedupe route, so it must be re-imported rather than publishing the scaffold. Currently **inactive** (`release-truth.md` §2.5). Dedupe keys on `workflow|status|lastNode` with `ALERT_DEDUPE_WINDOW_MINUTES` default 15.
- **Safe test environment.** Staging n8n with a throwaway workflow that errors deliberately.
- **Exact success evidence.** A forced error on a throwaway workflow produces **exactly one** founder WhatsApp page; a repeat inside the window is **suppressed**; the page body carries metadata only (workflow, status, last node, timestamp) and **no** payment references, tokens, PII or DSNs. Then the handler is linked as `settings.errorWorkflow` on the money ticks and on `backup.json`.
- **Rollback.** Unpublish; unlink `settings.errorWorkflow` from downstream workflows.

---

#### F — Observability / rollback / load

**LQ-F1 · Sentry live capture across four targets** — _Partial · CONFIG+EXTERNAL_

- **Source evidence.** `docs/ops/observability.md` §1: API `services/api/app/core/sentry.py`; three browser inits lazily loaded via `app/sentry-init.tsx` (deliberately **not** `withSentryConfig`, to keep the ~63 KB SDK out of first-load JS and inside the ≤ 150 KB gz budget). PII scrubber proven by `services/api/tests/test_sentry_scrubber.py` and matching vitest coverage in `@vergeo/observability`. Smoke script `scripts/ops/sentry_smoke.sh`. **Blocked historically by an external factor:** Sentry `create_project` returned 403 on 2026-07-20 (`docs/production-readiness/2026-07-20/observability-live-evidence.md`).
- **Safe test environment.** Staging first, using the **temporary** protected test endpoints (`ENABLE_SENTRY_TEST_ENDPOINT`, `INTERNAL_SENTRY_TEST_TOKEN`, `SENTRY_TEST_SECRET`).
- **Exact success evidence.** **Four** events visible in Sentry tagged `test_event=true`, one per target, each carrying the correct `release` = git SHA and `application` tag; and a manual inspection of one event confirming **no phone, email, token or address survived the scrubber**. Then disable the test endpoints or rotate the tokens.
- **Rollback.** Unset the DSNs — every target is a strict no-op without one, so removing the DSN fully disables capture with no deploy.

**LQ-F2 · Uptime monitor + alert actually fires** — _Absent · CONFIG+EXTERNAL_

- **Source evidence.** `infra/uptimerobot.md`; `docs/ops/observability.md` founder actions. Last audit recorded uptime alerting as **NOT_AUDITABLE**, which is not a pass.
- **Safe test environment.** Point a monitor at a staging health URL and take it down deliberately.
- **Exact success evidence.** A monitor on `/healthz` transitioning to DOWN and a **received** alert (with timestamp and channel), then recovery to UP. A configured-but-never-fired monitor is not evidence — the fire is the evidence.
- **Rollback.** Pause the monitor.

**LQ-F3 · Rollback drill (frontends + API + DB)** — _Absent · CONFIG_

- **Source evidence.** `docs/production-readiness/2026-07-20/ops-drills/rollback-verification/NOT_RUN.md` — verdict **FAIL** for G9/LIVE-10, aborted before mutating because `DEPLOYED_API_DIGEST=UNKNOWN`, the API was 502, and live migration tip had drifted. Runbook `infra/ROLLBACK.md`; API path `infra/redeploy-api.sh`; frontend path `scripts/ops/vercel_promote.sh`.
- **Safe test environment.** **Staging plane** — the drill is now runnable there without touching production, which was not true when the drill was first aborted.
- **Exact success evidence.** A harmless deploy followed by rollback of all four surfaces, with: the previous and restored Vercel `dpl_` ids per app; the previous and restored **API image digest** (must not be `unknown` — see LQ-D1); the DB tip before and after; wall-clock elapsed; and health/critical routes green after the rollback.
- **Rollback.** The drill _is_ the rollback. Its precondition is a recorded immutable previous version.

**LQ-F4 · Load 100 cc, p95 < 500 ms, invariants clean** — _Partial · FOUNDER_

- **Source evidence.** `load/k6/checkout-load.js`, `load/k6/browse-load.js`, `load/invariant-check.py`, `load/README.md` — all delivered and offline-validated (`node --check`, `py_compile`) per `docs/ops/load-test-results.md`. That document states in terms that **no p95 figures are fabricated** and the results table stays empty. Encoded thresholds: checkout `p95<500`, `http_req_failed<0.01`, `oversell_errors==0`; browse `search p95<400`, `plp p95<400`, `suggest p95<250`.
- **Safe test environment.** Staging plane, seeded (LQ-D8), with a **Lenco stub** — never sandbox or production Lenco under load.
- **Exact success evidence.** A completed run pasting p50/p95/p99, error rate, `oversell_errors`, `orders_created` into the `load-test-results.md` table, **plus `invariant-check.py` exiting 0**. The interpretation rule is already written and must be honoured: thresholds green **but** invariant-check failing = **FAIL regardless of latency**, because a money bug hid under load. Include the deliberately-scarce-listing contention burst named in the follow-ups.
- **Rollback.** Restore staging from its dump if the run leaves inconsistent inventory.

---

#### G — Cloudinary Clips cost guard

**LQ-G1 · F-V4 — plan and credit headroom** — _Partial, new evidence · EXTERNAL_

- **Source evidence.** **Queried read-only this window** (Cloudinary MCP `get-usage-details`, `last_updated: 2026-07-31`): plan **`Free`**; credits `0.37 / 25` used (**1.48 %**); `seconds_delivered.usage = 0` — **no video has ever been delivered**, consistent with the `clips` flag being off and the schema absent; 96 resources, 156 derived; `video_max_size_bytes = 104857600` (100 MB), which comfortably accommodates the ≤ 80 MB-per-clip design in `docs/plan/m17-video-feed.md`. Repo-side, `clip-cost-runbook.md` §6 marks F-V4 "**NOT resolved — deliberately safed**", and the safing is structural: with the flag off there is no upload path, so **no clip can spend a credit**.
- **What this evidence does and does not settle.** It **settles** headroom — 24.63 of 25 monthly credits are unused and image/PWA usage is negligible. It does **not** settle whether **eager video transcode** is permitted and at what per-second credit rate on the `Free` plan; that is the remaining half of F-V4 and it determines whether `clip_cost_rates` is right.
- **Safe test environment.** Cloudinary account console (read) + a **single** test upload on a non-production cloud or folder before the flag is flipped.
- **Exact success evidence.** A recorded statement of: the plan tier at the moment of check, whether eager video transcode is enabled, and the **observed** credit cost of one real 60 s clip transcoded to 480p + 720p + WebP poster — then that observed rate compared to `clip_cost_rates`. Drift > ~15 % means the config is wrong; fix the **config, not the code** (runbook §3).
- **Rollback.** `clips` flag → `false` (config, audited); uploads stop immediately, and per the guard's design the feed stays shoppable.

**LQ-G2 · Kill-switch drill (`clip-cost-runbook.md` §4)** — _Absent · FOUNDER_

- **Source evidence.** Guard `services/api/app/services/clips/spend.py` (integer micro-USD, `Decimal` conversion, monthly `YYYY-MM` window in `clip_spend_monthly`, cap from `platform_config.clip_monthly_cap_usd`). Drill is six numbered steps in `clip-cost-runbook.md` §4. **Cannot be run today:** `clip_spend_monthly` does not exist on production (`0079` unapplied — LQ-D6).
- **Safe test environment.** Staging plane after `0076`–`0079` are applied there.
- **Exact success evidence.** All six steps, with **step 3 the one that matters**: with the switch tripped, `/clips` still shows **posters, captions, prices and a working add-to-cart**. Upload refusal must be a clear translated message (`clip_cost_kill_switch`, 503), not a stack trace. Reset restores uploads. Every flip and reset appears in `audit_log` with an actor. The runbook states the point plainly: _does the thing still work when it fires?_
- **Rollback.** Restore `clip_monthly_cap_usd`; call the audited reset action.

**LQ-G3 · Clips dark-ship posture** — _Implemented · CODE_

- **Source evidence.** `0077_clip_feature_flags.sql` inserts `clips` and `clips_comments` as **`false`**; `services/api/app/services/clips/flags.py::_flag_enabled` returns `False` on a **missing** row _and_ on a read failure — fail-closed. Live: the tables and flag rows **do not exist** (`release-truth.md` §2.1), which is a stronger posture than "flagged off".
- **Safe test environment.** N/A.
- **Exact success evidence.** Met. After LQ-D6 applies the migrations, re-assert as "row exists **and** is `false`".
- **Rollback.** N/A.

**LQ-G4 · Monthly spend reconciliation** — _Absent · FOUNDER_

- **Source evidence.** Method in `clip-cost-runbook.md` §3: `GET /admin/clips/analytics` (ours, the guard's authority) vs the Cloudinary usage dashboard (the invoice's authority), recorded **on the same day each month**.
- **Safe test environment.** Read-only on both sides.
- **Exact success evidence.** Two numbers for the same month with the drift stated as a percentage. > ~15 % ⇒ correct `clip_cost_rates`. Only meaningful once clips are live; before that, LQ-G1's single-clip measurement is the substitute.
- **Rollback.** N/A.

---

#### H — WAHA private-pilot prerequisites (nothing enabled by this pebble)

> Every row here is **prerequisite-only**. D35 makes the founder the **sole approver at every gate** and states that **production is never inferred from "code complete"**. Nothing in this document authorises a pilot start.

**LQ-H1 · R1 pre-flight** — _Absent · CONFIG_

- **Source evidence.** `docs/plan/intake-pilot-checklist.md` §1 (nine unchecked boxes) mirroring `docs/ops/waha-vendor-intake.md` R1. **None can be ticked today:** `0072`–`0075` are unapplied on production, the `waha_vendor_intake` flag row does **not exist**, no WAHA host exists (`infra/docker-compose.yml` defines **no** WAHA service; `waha` appears only in `infra/.env.example` names and the two n8n JSONs), and neither `waha-intake-sweeps.json` nor `waha-intake-digest.json` has been imported (`release-truth.md` §2.5 — D35's "no active WAHA workflow" holds **by absence**, which is stronger than "imported but inactive").
- **Safe test environment.** An **isolated** WAHA host that is not co-tenant with Vergeo5 `api`/`caddy`/`n8n` or with ZedApply (NB-8).
- **Exact success evidence.** Every §1 box ticked with a name and date, including: `waha_vendor_intake` row exists and reads `false`; `waha_intake_vendor_allowlist` holds **only** hand-picked pilot vendor IDs; all six `WAHA_INTAKE_*` secrets present in the isolated host's secret store and **not** in the repo; `INTERNAL_INTAKE_TOKEN` set to a non-default value; webhook reachable **only** over TLS and only from `WAHA_INTAKE_ALLOWED_IPS`; both n8n workflows imported and confirmed **inactive**.
- **Rollback.** `waha_vendor_intake = false` — the canonical kill switch, admin-write, `config_audit`-logged, and the **first** check in the ingestion path.

**LQ-H2 · NB-7 three-way number separation** — _Absent · FOUNDER_

- **Source evidence.** D35 and `waha-vendor-intake.md` §1: a shared `waha.vergeo.company` session already runs under the wider "Convergeo" agency brand; a ban on that number must never contaminate Vergeo5's official Cloud API notifications.
- **Safe test environment.** N/A — a fact about numbers.
- **Exact success evidence.** Written into the checklist §10 Stage 1: `WAHA_INTAKE_SENDER_E164` ≠ the Cloud API sender ≠ any `waha.vergeo.company`/ZedApply/agency sender. Three distinct `+260` numbers, listed.
- **Rollback.** Do not start the pilot.

**LQ-H3 · NB-8 host / compartment isolation** — _Absent · CONFIG_

- **Source evidence.** D35; `waha-vendor-intake.md` §1 records that the OCI Always-Free VM co-hosts Vergeo5 api/caddy/n8n **plus** WAHA and ZedApply `zedcv-backend` — noisy-neighbour and blast-radius risk is real and named.
- **Safe test environment.** N/A — an infrastructure fact.
- **Exact success evidence.** A written confirmation of which host/compartment runs WAHA and that it is not the Vergeo5 API host, with the separation observable (distinct instance/compartment id).
- **Rollback.** Do not start the pilot.

**LQ-H4 · Vendor consent enrolment + disenrolment** — _Absent · FOUNDER/LEGAL_

- **Source evidence.** `intake-pilot-checklist.md` §2; D35 §12 (Zambia DPA + WhatsApp ToS; explicit opt-in; content minimised and short-retention-swept).
- **Safe test environment.** Real pilot vendors — there is no synthetic substitute for informed consent.
- **Exact success evidence.** An `intake_vendor_bindings` row per vendor with `consent_source` recorded and a timestamp; evidence each vendor was told **in language they use** which number to message, that content becomes a **private draft only**, that nothing publishes until they submit and Vergeo5 approves, and how to opt out; **disenrolment tested** for at least one vendor (`opted_out_at` set ⇒ their messages drop as `dropped_unverified`); and confirmation that **no vendor was cold-messaged** on the intake number.
- **Rollback.** Set `opted_out_at`; flip the flag off.

**LQ-H5 · Live drill dispositions + kill-switch rehearsal** — _Absent · FOUNDER_

- **Source evidence.** `intake-pilot-checklist.md` §3 (a 7-row table with empty Observed/Date/Operator columns) and §4. The automated half is already continuous: `services/api/tests/e2e/test_intake_pilot.py` proves 16 properties in CI including `test_valid_sha256_signature_is_still_refused` — lane separation asserted by test, because the pinned WAHA `2026.5.1` contract requires `X-Webhook-Hmac-Algorithm: sha512` over the **raw** body. The checklist is explicit that passing tests are a **precondition, not evidence of a pilot**.
- **Safe test environment.** Real pilot infrastructure — the checklist exists precisely because the suite cannot prove physical facts about a deployment.
- **Exact success evidence.** All seven §3 rows filled with the **observed** audit disposition (`draft_created`, `draft_created ×1`, `dropped_unverified`, `dropped_group`, `rejected_auth`), plus the assertion that after the drill `vendor_listings` contains **no** row that reached `active` without the admin step. §4: with work in flight, flag → `false`; subsequent events audit `dropped_flag_off`; the pilot vendor's **existing draft is intact and still openable**; **Lane 1 is unaffected** (a normal order notification still delivers).
- **Rollback.** The kill switch **is** the rollback, and rehearsing it is the row.

**LQ-H6 · Retention sweep + workflows imported inactive** — _Absent · CONFIG_

- **Source evidence.** `intake-pilot-checklist.md` §5; sweeps driven by `INTERNAL_INTAKE_TOKEN`; workflows `infra/n8n/waha-intake-{sweeps,digest}.json` — **not present on the n8n instance**.
- **Safe test environment.** Isolated pilot infrastructure.
- **Exact success evidence.** After the retention window: `intake_messages.raw_excerpt` is `NULL` for old rows while message id, kind and **audit dispositions survive**; expired **unredeemed** review links are gone and **redeemed** ones kept; a log spot-check shows **no raw message body and no full MSISDN** (asserted in CI by `test_logs_never_carry_a_raw_body_or_a_full_msisdn`, to be confirmed on real logs).
- **Rollback.** Deactivate the sweep workflows; flag off.

---

#### I — SEO

**LQ-I1 · `robots.txt` correct on the live host** — _Partial · CODE done, verification outstanding_

- **Source evidence.** `apps/customer/app/robots.ts` — allows `/`, disallows the suffix list from `apps/customer/lib/seo/sitemap-eligibility.ts::ROBOTS_DISALLOW_SUFFIXES` (`/checkout`, `/cart`, `/account`, `/admin`, `/search`, `/ask`, `/calendar`, `/compare`, `/supplies`, `/services/post-job`, each with and without a trailing slash), emits `sitemap: ${siteUrl}/sitemap.xml` and `host`. Separate `apps/admin/app/robots.ts` for the admin origin. Tested: `apps/customer/app/robots.test.ts`.
- **Safe test environment.** Production, read-only.
- **Exact success evidence.** `curl https://www.vergeo5.com/robots.txt` returning the disallow list with the **production** `siteUrl` (not a Vercel preview host, not localhost), and the admin origin returning its own restrictive robots.
- **Rollback.** `NEXT_PUBLIC_SITE_URL`/equivalent env fix + redeploy; or Vercel promote-previous.

**LQ-I2 · `sitemap.xml` + shards serve live and are fresh** — _Partial · CODE done, verification outstanding_

- **Source evidence.** `apps/customer/app/sitemap.xml/route.ts` (index) + `apps/customer/app/sitemap/[id]/route.ts` (shards); builder `apps/customer/lib/seo/sitemap-build.ts`; eligibility `sitemap-eligibility.ts`; event sitemap `sitemap-events.ts`; sources `sitemap-sources.ts`. Tests: `sitemap-build.test.ts`, `sitemap-eligibility.test.ts`, `sitemap-events.test.ts`, `app/sitemap-root.test.ts`.
- **Safe test environment.** Production, read-only.
- **Exact success evidence.** The index returns 200 and lists shards; **each** shard returns 200 with absolute production URLs; a spot-checked product/event URL from the sitemap returns **200 and is indexable** (not `noindex`); and **no demo/excluded listing appears** (D25 requires demo content excluded from public search — cross-check against the demo-exclusion path).
- **Rollback.** As LQ-I1.

**LQ-I3 · Titles / meta descriptions per indexable route** — _Partial · CODE_

- **Source evidence.** Per-route `generateMetadata` present across `apps/customer/app/[locale]/(shop)/{page,p/[slug],c/[...slug],v/[slug],e/[slug],events,services,categories,search}/page.tsx` and the marketing/legal tree. i18n enforcement: `scripts/ci/i18n-lint.mjs` flags `<meta content="…">` copy as a hardcoded string, so descriptions are message-keyed by construction.
- **Safe test environment.** Production, read-only, plus Lighthouse SEO (LQ-K2).
- **Exact success evidence.** A per-route table of the **rendered** `<title>` and `<meta name="description">` for the top ~12 indexable routes, confirming: unique per route, length within search-result truncation, correct locale, and no placeholder/lorem text. This is the row most likely to reveal thin or duplicated copy — it overlaps LQ-J4.
- **Rollback.** Message-key edits + redeploy.

**LQ-I4 · Canonical + hreflang alternates** — _Partial · CODE done, verification outstanding_

- **Source evidence.** `alternates`/`canonical` set across the shop and marketing trees (≈20 route files, e.g. `(shop)/p/[slug]/page.tsx`, `(shop)/c/[...slug]/page.tsx`, `(shop)/v/[slug]/page.tsx`, `(marketing)/legal/*`). Locales `en | bem | nya | fr` are public (`packages/i18n/src/locales.ts::PUBLIC_LOCALES`; `zh` is defined but **not** public).
- **Safe test environment.** Production, read-only.
- **Exact success evidence.** For one product, one category, one event and one vendor page: a **self-referential absolute canonical** on the production host, and `hreflang` alternates covering exactly the four public locales plus `x-default` — with `zh` **absent** from the public alternates (it is in `LOCALES` but not `PUBLIC_LOCALES`; a leaked `zh` alternate would be a defect).
- **Rollback.** As LQ-I1.

**LQ-I5 · Structured data validates** — _Partial · EXTERNAL_

- **Source evidence.** Shared emitter `packages/ui/src/seo/json-ld.tsx` (+ `json-ld.test.tsx`); consumers `(shop)/p/[slug]`, `(shop)/c/[...slug]`, `(shop)/v/[slug]`, `(shop)/e/[slug]` (with a dedicated `_components/event-jsonld.tsx` and its test), `(shop)/page.tsx`, `(marketing)/sell`, `(marketing)/help/[slug]`.
- **Safe test environment.** Google Rich Results Test against **live production URLs** (it cannot reach a private preview).
- **Exact success evidence.** A Rich Results pass **per type** — Product (with `offers` in **ZMW** and the correct availability), Event, Organization, BreadcrumbList — with **zero errors**; warnings listed and each accepted or fixed. A screenshot or exported report per type.
- **Rollback.** JSON-LD is additive; remove the offending emitter and redeploy.

**LQ-I6 · Indexing posture while `public_launch=false`** — _Partial, open question · CODE+CONFIG_

- **Source evidence.** Route-level robots directives are deliberate and varied: `beta/page.tsx` `index:false, follow:false`; `ask`, `services/post-job`, `clips/[id]` `index:false`; `clips/page.tsx` `index:false, follow:true`; `search`, `categories`, `events`, `services` gate `index` on filter/state; `v/[slug]` indexable when found, `index:false` when not; `p/[slug]` `index:false` on the not-found branch. But `robots.ts` itself is **globally `allow: "/"`** and does not vary with `public_launch`.
- **The open question.** During an **invite-gated beta**, a crawler that follows the sitemap reaches pages that a human visitor cannot use without an invite code. That is either (a) intentional SEO warm-up — index the catalogue now so organic traffic exists at public launch, accepting a soft-404-ish user experience for crawled arrivals; or (b) a leak that should be closed by serving `noindex` while `public_launch=false`. **The repository does not record a decision either way.** Candidate ADR `R02-ADR-03` below.
- **Safe test environment.** Production, read-only, plus a crawl simulation.
- **Exact success evidence.** Once the posture is decided: fetch a product URL as Googlebot and confirm the intended directive; and confirm the sitemap advertises only URLs consistent with that posture.
- **Rollback.** If (b) is chosen and implemented as a flag-driven `noindex`, flipping `public_launch` reverses it with no deploy — which is the argument for implementing it that way rather than hard-coding.

---

#### J — Vernacular + copy

**LQ-J1 / LQ-J2 · Bemba and Nyanja coverage** — _Partial (58.7 % each) · CODE_

- **Source evidence (measured this window).** Counting leaf string values in `packages/i18n/messages/<locale>/*.json`:

  | Locale | Leaf strings | % of EN    | Namespaces missing entirely |
  | ------ | ------------ | ---------- | --------------------------- |
  | `en`   | 4 044        | 100 %      | — (19 namespaces)           |
  | `bem`  | 2 373        | **58.7 %** | `legal`, `admin`, `clips`   |
  | `nya`  | 2 373        | **58.7 %** | `legal`, `admin`, `clips`   |
  | `fr`   | 3 610        | 89.3 %     | `clips`                     |
  | `zh`   | 3 610        | 89.3 %     | `clips`                     |

  Note this **corrects the count in `AGENTS.md`**, which states 17 namespaces with `bem`/`nya` at 13/17 and `ai` among the EN-only set; the tree now has **19** EN namespaces, `bem`/`nya` carry **16** including `ai`, and the genuinely missing three are `legal`, `admin`, `clips`. Missing keys never render a raw key path — `packages/i18n/src/request.ts` deep-merges over EN at runtime, so a gap renders **English**. `bem`/`nya` are in `PUBLIC_LOCALES`.

- **Safe test environment.** Local/CI (`node scripts/ci/i18n-lint.mjs`) + a visual pass on staging.
- **Exact success evidence.** For a **beta**: 100 % coverage of the _core customer flow_ namespaces — `nav`, `common`, `catalog`, `search`, `checkout`, `orders`, `account`, `auth`, `notifications` — measured by the same leaf count, with the residual gap explicitly limited to `admin` (staff-only, EN acceptable per D27) and `clips` (dark). For **public launch**: add `legal`, but **only human-reviewed** — D27 forbids machine translation for checkout/payment/legal copy without review.
- **Rollback.** Removing a locale file falls back to EN safely; there is no broken state.

**LQ-J3 · Human review of vernacular strings** — _Absent · FOUNDER_

- **Source evidence.** D27 requires Bemba/Nyanja to be **human-reviewed**, and forbids machine translation for checkout/payment/legal copy without review. No reviewer, date or sign-off exists in the repo for the 2 373 existing `bem`/`nya` strings.
- **Safe test environment.** N/A — human review.
- **Exact success evidence.** A named reviewer, a date, and a per-namespace sign-off, with **checkout, payments, orders and notifications reviewed first** (these are the money-adjacent strings D27 singles out). Record corrections made.
- **Rollback.** Revert a namespace to EN-only; the runtime deep-merge makes that safe.

**LQ-J4 · Professional EN copy pass** — _Absent · FOUNDER_

- **Source evidence.** Copy is fully externalised (4 044 EN leaf strings, zero hardcoded strings enforced blocking in `perf.yml` per `docs/plan/i18n-audit.md`) — the _mechanism_ is excellent. But **no editorial review** is recorded. One concrete instance of stale copy is already documented: `docs/plan/i18n-audit.md` notes the retained legacy `privacy.*` keys are **dead copy** — `deletePhrasePlaceholder` says "DELETE MY DATA" while the page's actual confirmation phrase is "DELETE MY ACCOUNT".
- **Safe test environment.** Staging, read-only.
- **Exact success evidence.** A reviewed pass over the three copy classes with a named reviewer and date: **trust-critical** (escrow explainer "You paid → Held by Vergeo5 → Released", checkout consent, payment states, refund/returns), **legal** (terms, privacy, returns, vendor agreement — these are also the D27 no-machine-translation set), and **marketing** (home, `/sell` vendor pitch, category landing). Deliverable: a diff of message keys changed, plus an explicit list of dead keys deleted.
- **Rollback.** Message-key revert; no schema or behaviour impact.

---

#### K — Browser-led verification

> These four rows exist because a Lighthouse run in CI against `localhost:3000` with a synthetic route list is **not** the same fact as a real browser on a real deployed page with real content. `lighthouserc.json` currently collects five hard-coded localhost URLs including a seeded `/en/p/smartphone-x1`.

**LQ-K1 · Accessibility on a deployed surface** — _Partial · FOUNDER/Ops_

- **Source evidence.** `e2e/specs/a11y-smoke.spec.ts` runs `@axe-core/playwright` with `withTags(["wcag2a","wcag2aa"])` over `/`, `/cart`, `/checkout` and fails on **critical or serious** violations only. Its own comment concedes it is a "cheap axe smoke … advisory rules can be tightened once staging content is stable". Lighthouse a11y thresholds live in `lighthouserc.json` (checkout asserts `accessibility ≥ 0.9`).
- **Safe test environment.** Staging (seeded) in a real browser; production read-only for the public routes.
- **Exact success evidence.** Axe run over a **wider** route set than three — home, PLP, PDP, vendor profile, event page, search, cart, checkout, account — with **zero critical/serious** violations; plus three things axe cannot check: a **full keyboard-only** traversal of the checkout (every control reachable and operable, visible focus ring throughout), a **screen-reader** pass over the checkout's payment step, and colour-contrast confirmation against the `packages/ui` tokens. Lighthouse A11y ≥ 95 on the deployed URL (CLAUDE.md budget 7).
- **Rollback.** N/A (verification).

**LQ-K2 · Lighthouse mobile Perf/SEO/A11y on the deployed URL** — _Partial · FOUNDER/Ops_

- **Source evidence.** `lighthouserc.json` collects **mobile, 360×740, 4× CPU slowdown, 1600 kbps** — the right emulation — but against `http://localhost:3000`. Release gate G19 (Lighthouse budgets) is recorded **FAIL** in `release-gates.md`. CLAUDE.md budget 7 requires **Perf ≥ 90 / SEO ≥ 95 / A11y ≥ 95**; note the committed config asserts **lower** thresholds for `/checkout` (perf ≥ 0.5, seo warn ≥ 0.4), which is defensible for an auth-gated funnel step but means a green CI run does **not** demonstrate the CLAUDE.md budget.
- **Safe test environment.** Staging (seeded) and production public routes.
- **Exact success evidence.** Lighthouse mobile reports for home, PLP, PDP and search on the **deployed** host meeting **Perf ≥ 90 / SEO ≥ 95 / A11y ≥ 95**, with the raw JSON attached. Checkout reported separately against its own stated thresholds and the divergence from budget 7 explicitly accepted or fixed.
- **Rollback.** N/A.

**LQ-K3 · 360 px one-handed responsive sweep** — _Absent · FOUNDER/Ops_

- **Source evidence.** 360px-first is a founding constraint (CLAUDE.md; `lighthouserc.json` screen emulation). Mountain criteria demand "daily-driver one-handed 360 px" for the vendor portal and "≤ 4 steps at 360 px" for checkout (`docs/plan/launch-checklist.md` §1 M07/M12). **No sweep artifact exists.**
- **Safe test environment.** Staging (seeded), real device or 360 px emulation.
- **Exact success evidence.** A screenshot set at 360 px across the customer critical path (home → PLP → PDP → cart → 4-step checkout → order) **and** the vendor daily-driver path (KYC → create listing → orders → payouts), each confirming: no horizontal scroll, primary actions inside thumb reach, no truncated money or address strings, and the checkout completing in ≤ 4 steps.
- **Rollback.** N/A.

**LQ-K4 · Fast-3G LCP ≤ 2.5 s on the deployed surface** — _Partial · FOUNDER/Ops_

- **Source evidence.** Budget in CLAUDE.md 7 and in the M05 mountain criterion. Throttling is configured in `lighthouserc.json`; bundle ceilings enforced by `scripts/ci/bundle-guard.mjs` (≤ 150 KB gz, `REGRESSION_TOLERANCE_KB` raised 0.5 → 2.0 once to absorb the PWA baseline shift — recorded in `00-status.md` Wave-18). Image discipline: `scripts/ci/image-lint.mjs`; Cloudinary `f_auto,q_auto` per D26.
- **Safe test environment.** Deployed staging/production with **Fast 3G** throttling from a Lusaka-representative network path if possible.
- **Exact success evidence.** Measured LCP ≤ 2.5 s at 360 px / Fast-3G on **home and PDP** against the deployed host, plus the transferred-bytes figure for a cold PDP load — the data-cost frugality guardrail deserves a number, not an adjective. Cross-check against the Clips S1 target (≤ 5 MB for a 10-clip session, `e2e/specs/clips-feed.spec.ts`) if clips are in scope for the beta.
- **Rollback.** N/A.

---

## 4. Candidate ADRs (proposed, not decided — `00-decisions.md` untouched)

**R02-ADR-01 — Promote the staging plane from "not a prerequisite" to "the standard test environment for every launch drill."**
D30 (2026-07-19) chose a hybrid path explicitly _because_ no separable staging stack existed, deferring VE-P08 to Wave 4. That premise no longer holds: `deploy-staging.yml` run #9 deployed API + Vercel Preview + smoke end to end on 2026-08-01, with machine-enforced production separation in both CI and the API process. **Proposal:** amend D30 to make the staging plane the required target for S1–S6, the load run, the rollback drill, the Clips kill-switch drill and the browser-led sweeps — removing the "improvise an isolated target" language. **Consequence:** raises the evidentiary bar; costs nothing new. **Founder decision required.**

**R02-ADR-02 — Split G7 into two gates that are currently conflated.**
"Backups and restore proof" today mixes a _continuously green CI drill_ (LQ-E1) with an _un-run live timed restore_ (LQ-E3). Because the CI drill now passes nightly, a reader can mistake G7 for satisfied. **Proposal:** G7a = self-contained restore drill green (**satisfied**); G7b = dated live dump (RPO ≤ 24 h) + timed live restore (RTO ≤ 30 min) logged in `drill-log.md` (**not satisfied; blocking**). **Consequence:** removes an ambiguity that has already produced conflicting readings across dated packs.

**R02-ADR-03 — Decide the indexing posture during invite-gated beta.**
See LQ-I6. Options: (a) index the public catalogue during beta to warm organic traffic, accepting crawled arrivals hitting an invite gate; (b) serve `noindex` while `public_launch=false`, flipping automatically with the flag. **Recommendation: (b)**, implemented as a flag-driven directive so the flip needs no deploy — matching how `public_launch` already works for the beta gate. **Founder decision required.**

**R02-ADR-04 — State the launch position on vernacular coverage.**
D27 orders the languages but sets no coverage threshold. Bemba/Nyanja sit at 58.7 % of EN by leaf count, all gaps falling back to English. **Proposal:** beta requires 100 % of the core customer-flow namespaces (`nav`, `common`, `catalog`, `search`, `checkout`, `orders`, `account`, `auth`, `notifications`) human-reviewed; `admin` stays EN-only permanently; `legal` is required for public launch and **must** be human-reviewed per D27. **Consequence:** converts P2 gate G18 from an unbounded "FAIL" into a measurable target.

**R02-ADR-05 — Require a traceable `git_sha` before any promote.**
The last live probe found `GIT_SHA=unknown` on the production API (2026-07-23), and the rollback drill aborted for exactly this reason. **Proposal:** make a non-`unknown` `git_sha` on `/fingerprint` a hard precondition for promoting anything and for declaring any live gate PASS. **Consequence:** cheap; closes the loop that made G9 unprovable.

**R02-ADR-06 — Record what half of F-V4 the 2026-08-01 Cloudinary reading closes.**
Plan `Free`, 0.37/25 credits (1.48 %), zero seconds of video ever delivered, 100 MB video ceiling. Headroom is no longer an open question; the **eager-video-transcode permission and per-second credit rate** still are. **Proposal:** re-scope F-V4 to that residual question so it stops reading as wholly unknown.

---

## 5. Unresolved founder decisions

| Ref                  | Question                                                                     | Blocks                                                                                                               | Notes                                                                                                                                                                  |
| -------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **F2**               | PACRA annual returns + **company** TPIN                                      | Lenco settlement, ZRA invoicing                                                                                      | Personal TPIN will not do (D13).                                                                                                                                       |
| **F4**               | Zambian counsel opinion on Lenco-held escrow under NPS Act 2026              | **Real money — hard gate**                                                                                           | Brief ready: `docs/ops/f4-escrow-legal-review-brief.md`. LQ-A10.                                                                                                       |
| **F5**               | Meta Business + WhatsApp Cloud API activation + template approval            | Live notifications, OTP delivery, **every** ops alert (backup + shared failure alert page the founder over WhatsApp) | Under-appreciated coupling: LQ-E4/E5 cannot deliver a page without F5.                                                                                                 |
| **F6**               | Courier / bus-freight MOUs                                                   | Nationwide fulfilment promises                                                                                       | Post-beta acceptable (D16).                                                                                                                                            |
| **F7**               | Remaining 6 design HTML files                                                | Merch variant library only                                                                                           | Tokens already locked.                                                                                                                                                 |
| **F8**               | Confirm or invert the COD ≤ K500 cap                                         | Checkout fraud posture                                                                                               | Open since 2026-07-06; D12 flags the founder's original reply as ambiguous. Inverting it inverts the fraud logic and is **not** recommended.                           |
| **F9a**              | Zamtel collections operator value                                            | `zamtel_collections` flag                                                                                            | LQ-B3.                                                                                                                                                                 |
| **F9b**              | Lenco sandbox + production credentials                                       | **All of section A**                                                                                                 | LQ-A11. The single highest-leverage unblock in this document.                                                                                                          |
| **F-V4**             | Cloudinary eager video transcode permission + per-second credit rate         | Clips flag flip                                                                                                      | Headroom now evidenced (LQ-G1); the rate is not.                                                                                                                       |
| **New — R02-ADR-01** | Make the staging plane the standard drill target?                            | Sequencing of every drill                                                                                            | §4.                                                                                                                                                                    |
| **New — R02-ADR-03** | Index or `noindex` during invite-gated beta?                                 | SEO posture, LQ-I6                                                                                                   | §4.                                                                                                                                                                    |
| **New — R02-ADR-04** | Vernacular coverage threshold for beta vs public?                            | LQ-J1/J2/J3, gate G18                                                                                                | §4.                                                                                                                                                                    |
| **New**              | Does the **controlled beta** carry Clips and/or the WAHA intake lane at all? | Scope of sections G and H                                                                                            | Both currently ship dark and **schema-absent** on production. Keeping both off through beta removes ~10 rows from the critical path at zero product cost. Recommended. |

---

## 6. Proposed implementation pebbles

Small, sequenced, **exclusive file ownership per pebble** so waves can run in parallel without collision. Each is docs-or-code-only as marked; none flips a flag or runs a drill without the founder.

### Wave R02-A — unblock the test environment (no dependencies)

| Pebble     | Title                                              | Class | Exclusive files                                                      | Depends on          |
| ---------- | -------------------------------------------------- | ----- | -------------------------------------------------------------------- | ------------------- |
| **RQ-P01** | Fix the staging synthetic seed                     | CODE  | `scripts/seed_staging.py`, `services/api/tests/test_seed_staging.py` | —                   |
| **RQ-P02** | Add `git_sha` promotion guard to the live verifier | CODE  | `scripts/ops/verify_live.sh`                                         | —                   |
| **RQ-P03** | Split G7 into G7a/G7b in the gate register         | DOCS  | `docs/production-readiness/2026-07-18/consolidated/release-gates.md` | R02-ADR-02 accepted |

> **RQ-P01 is the critical path.** Until staging seeds, there is no catalogue to check out, load-test or audit — it silently gates LQ-A1–A9, LQ-C1–C4, LQ-D4, LQ-F4 and all of section K.

### Wave R02-B — evidence plumbing (depends on A)

| Pebble     | Title                                                                                       | Class | Exclusive files                                             | Depends on          |
| ---------- | ------------------------------------------------------------------------------------------- | ----- | ----------------------------------------------------------- | ------------------- |
| **RQ-P04** | Point Lighthouse collection at a configurable deployed base URL (keep localhost as default) | CODE  | `lighthouserc.json`, `scripts/ci/validate-lighthouserc.mjs` | RQ-P01              |
| **RQ-P05** | Widen the axe smoke route set (home/PLP/PDP/vendor/event/search added)                      | CODE  | `e2e/specs/a11y-smoke.spec.ts`                              | RQ-P01              |
| **RQ-P06** | Vernacular coverage reporter — leaf-count per locale per namespace, advisory                | CODE  | `scripts/ci/i18n-lint.mjs` (new `--coverage` mode only)     | R02-ADR-04 accepted |
| **RQ-P07** | Correct the i18n namespace counts in `AGENTS.md` (17→19, 13/17→16/19)                       | DOCS  | `AGENTS.md`                                                 | —                   |

> RQ-P04 and RQ-P05 both touch the browser-verification story but **share no file**. RQ-P06 owns `i18n-lint.mjs` exclusively; RQ-P07 owns `AGENTS.md` exclusively.

### Wave R02-C — SEO posture (depends on the ADR, not on A)

| Pebble     | Title                                                         | Class | Exclusive files                                                   | Depends on                  |
| ---------- | ------------------------------------------------------------- | ----- | ----------------------------------------------------------------- | --------------------------- |
| **RQ-P08** | Flag-driven beta indexing posture                             | CODE  | `apps/customer/app/robots.ts`, `apps/customer/app/robots.test.ts` | **R02-ADR-03 = option (b)** |
| **RQ-P09** | Title/description audit table for the top 12 indexable routes | DOCS  | `docs/plan/r02/seo-metadata-audit.md` (new)                       | —                           |

> RQ-P08 must not proceed on option (a). It is listed so the work is scoped, not so it is assumed.

### Wave R02-D — operator execution (founder; not agent work)

Strictly ordered — each depends on the previous:

1. **F9b credentials** on the staging host → unblocks everything below.
2. **LQ-A1 → LQ-A7 → LQ-A3 → LQ-A8 → LQ-A9** (collection → idempotency → release → payout → refund), then **LQ-B2** (Airtel, fresh order) and **LQ-A2** (card).
3. **LQ-A6** false-success matrix and **LQ-A5** KYC drill — independent of each other, both after step 2's environment is proven.
4. **LQ-A4** activate money n8n **only after** S1 and S3 pass.
5. **LQ-E2 → LQ-E3** (dated dump, then timed restore) — **prerequisite for LQ-D6** applying `0072`–`0079` to production.
6. **LQ-E4 / LQ-E5** backup + failure-alert activation — **requires F5** for WhatsApp delivery.
7. **LQ-F1 → LQ-F2** Sentry then uptime; **LQ-F3** rollback drill on staging; **LQ-F4** load run.
8. **LQ-K1–K4** browser-led sweeps on the seeded staging plane.
9. **LQ-A10 (F4 counsel)** — runs in parallel throughout; **gates real money regardless of every row above.**

Clips (section G) and WAHA (section H) execute **only** if the founder scopes them into the beta; otherwise both remain dark and schema-absent, and their rows carry forward unchanged.

---

## 7. Related

- `docs/plan/00-status.md` · `docs/plan/00-decisions.md` — source of truth (**not modified by this pebble**)
- `docs/production-readiness/2026-07-27/release-truth.md` — last consolidated snapshot; §2 above records where it has since drifted
- `docs/production-readiness/2026-07-18/consolidated/release-gates.md` — gate register (G0–G22, S0–S7)
- `docs/plan/launch-checklist.md` — founder-facing go/no-go with evidence slots
- `docs/production-readiness/2026-07-22/money-drill-runbook.md` · `docs/ops/lenco/sandbox-money-drill.md` · `docs/ops/launch-gates-execution.md`
- `docs/ops/n8n-backup-and-alerts.md` · `docs/ops/drill-log.md` · `docs/ops/backup-restore-drill.md` · `infra/ROLLBACK.md`
- `docs/ops/observability.md` · `docs/ops/load-test-results.md` · `docs/plan/i18n-audit.md`
- `docs/ops/clip-cost-runbook.md` · `docs/plan/m17-video-feed.md`
- `docs/ops/waha-vendor-intake.md` · `docs/plan/intake-pilot-checklist.md`
- `scripts/ops/verify_live.sh` — the read-only production probe matrix
