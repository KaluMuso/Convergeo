# Implementation Wave Plan — Post Document-Audit Consolidation

**Date:** 2026-07-18  
**Inputs:** `master-reconciliation-register.md` · `panel-backlogs.md` · `release-gates.md` · `source-conflicts-and-decisions.md`  
**Constraint:** One pebble ≈ one exclusive file ownership wave; no production money enablement until staging gates PASS.

---

## Goal

Move CODE_COMPLETE money/KYC/panel work (#274, #288–#294) through **STAGING_VERIFIED** evidence, close remaining P0 ops gaps (n8n, migrations, RLS, monitoring, backup/restore), and only then consider real-money beta — without inventing founder decisions.

---

## Wave 0 — Founder decisions (parallel, non-code)

| Item                        | Decision ID | Output artifact                | Unblocks          |
| --------------------------- | ----------- | ------------------------------ | ----------------- |
| Zamtel collections          | FD-01       | Decision note + flag/UI policy | G14, PAY-05       |
| Admin RBAC model            | FD-02       | ADR or `00-decisions` update   | ADM-01/02, G15    |
| Role hook vs manual grants  | FD-03       | Written path                   | G0 / MR-S02       |
| Demo catalogue posture      | FD-04       | Merch plan                     | G11, CUST-02      |
| Phase-1 catalogue scope     | FD-06       | Class A-only **or** A–E claim  | MR-S05/S06 gating |
| FORCE RLS ticket tiers      | FD-07       | Enable vs exception            | G0 / MR-R01       |
| Legal counsel               | FD-08       | Written sign-off               | G13 / MR-L01      |
| Confirm DPO abandoned       | FD-09       | SoT note                       | MR-L03            |
| KYC orphan repair ownership | FD-12       | Ops runbook                    | DB-06             |

**Exit:** Decisions recorded; no silent defaults.

---

## Wave 1 — Staging money proof (P0)

**Owner:** Payments / API · **Depends:** Lenco sandbox credentials (ops)

| Order | Backlog          | Work                                                                | Exit evidence                         |
| ----- | ---------------- | ------------------------------------------------------------------- | ------------------------------------- |
| 1.1   | PAY-01 / MR-B01  | Sandbox MoMo prepaid → `CHARGE_RECEIVED`                            | SQL aggregates + redacted Lenco match |
| 1.2   | PAY-01           | Sandbox card prepaid → ledger                                       | Same                                  |
| 1.3   | PAY-03           | Webhook replay idempotency                                          | Single ledger txn                     |
| 1.4   | PAY-02 / MR-B01b | Release tick → `COMMISSION_CAPTURE` + `RELEASE_TO_VENDOR`; escrow→0 | #294 invariants                       |
| 1.5   | PAY-06 / G4      | E2E false-success suite (incl. COD isolation)                       | S6 PASS                               |
| 1.6   | API-08           | Status contract fields if customer still needs ledger confirmation  | CUST-08 residual closed               |

**Exit:** S1–S3 + S6 **STAGING_VERIFIED**. Do **not** enable production prepaid.

**Non-goals:** Live payouts, credential rotation, production backfills.

---

## Wave 2 — n8n critical workflows (P0)

**Owner:** Ops · **Depends:** Wave 1 staging money path for meaningful release/ticket drills

| Order | Backlog         | Work                                                                       | Exit evidence                          |
| ----- | --------------- | -------------------------------------------------------------------------- | -------------------------------------- |
| 2.1   | N8N-01 / MR-W01 | Import/activate `release-job` (+ order-jobs as needed) with internal token | Active + success execution; retry-safe |
| 2.2   | N8N-02 / MR-W02 | Activate `tickets-issue` + `event-release`                                 | Exactly-once ticket; QR verify         |
| 2.3   | N8N-04          | Prove recon mismatch alerting                                              | Actionable alert                       |

**Exit:** G5 staging PASS for release + tickets.

---

## Wave 3 — Database rollout + KYC (P0)

**Owner:** DB/Ops + API · **Depends:** Wave 0 FD-03/FD-07/FD-12; backup proof prep (OPS-03)

| Order | Backlog               | Work                                                                                          | Exit evidence                    |
| ----- | --------------------- | --------------------------------------------------------------------------------------------- | -------------------------------- |
| 3.0   | OPS-03 / N8N-03       | Backup artifact **before** migrate                                                            | Dated backup                     |
| 3.1   | DB-01 / MR-S01        | Reconcile `0051`/`0052` key/`0053`–`0055` per agreed target                                   | Staging `schema_migrations`      |
| 3.2   | DB-02 / MR-S11        | Apply `0056_kyc_integrity` per KYC report order (API understand statuses → migrate → clients) | Objects/trigger/view live        |
| 3.3   | DB-03                 | Enable role hook **or** attach FD-03 exception                                                | G0 role path                     |
| 3.4   | DB-04                 | FORCE RLS enable **or** FD-07 exception                                                       | G0 RLS                           |
| 3.5   | S5 / ADM-03 / VEND-01 | Staging KYC drill + orphan report                                                             | Privileges freeze without record |
| 3.6   | DB-06                 | Controlled manual orphan repair (no auto-upgrade)                                             | Orphans ticketed/cleared         |

**Exit:** G0/G12 staging path clear; production apply only after staging PASS + backup.

---

## Wave 4 — Deploy panel honesty + acquisition (P1 / residual P0 UI)

**Owner:** Frontend/platform · **Depends:** Vercel access

| Order | Backlog                    | Work                                                                                 | Exit evidence               |
| ----- | -------------------------- | ------------------------------------------------------------------------------------ | --------------------------- |
| 4.1   | OPS-07                     | Deploy customer/vendor/admin SHAs containing #289–#291 (+ #293 admin/vendor clients) | Vercel SHAs recorded        |
| 4.2   | CUST-01                    | Set `NEXT_PUBLIC_VENDOR_APP_URL`; redeploy customer                                  | G10 probe PASS              |
| 4.3   | CUST-03/04/05/07/10        | Re-probe categories/compare/SW/copy/calendar                                         | PRODUCTION_VERIFIED probes  |
| 4.4   | CUST-13                    | Customer storefront KYC badge alignment                                              | No bare-tier verified badge |
| 4.5   | CUST-08 / VEND-11 / ADM-11 | Eliminate residual prod localhost API fallbacks                                      | G2 hardened                 |

**Exit:** G1/G2/G10/G17 improved; still no real-money without Waves 1–3.

---

## Wave 5 — Observability, CI, rollback (P1)

| Order | Backlog         | Work                                             | Exit evidence       |
| ----- | --------------- | ------------------------------------------------ | ------------------- |
| 5.1   | OPS-01 / MR-O01 | Sentry projects + DSNs                           | Test events         |
| 5.2   | OPS-02          | Uptime monitors                                  | Green health checks |
| 5.3   | OPS-03          | Restore drill                                    | RPO/RTO doc         |
| 5.4   | OPS-05 / G9     | Rollback drill                                   | Timed procedure     |
| 5.5   | OPS-06 / MR-R05 | Blocking secret-scan + branch protection confirm | Screenshots/config  |
| 5.6   | API-09 / OPS-09 | Pin API image digest                             | Release ledger      |

**Exit:** G6/G7/G8/G9 no longer NOT_AUDITABLE for monitored paths.

---

## Wave 6 — Public positioning & scope features (after money beta)

| Order | Backlog           | Work                                           | Gate         |
| ----- | ----------------- | ---------------------------------------------- | ------------ |
| 6.1   | CUST-02 / MR-D01  | Execute FD-04 demo plan                        | G11          |
| 6.2   | OPS-08            | Legal artifact FD-08                           | G13          |
| 6.3   | PAY-05            | Zamtel UI matches FD-01                        | G14          |
| 6.4   | ADM-01/02         | RBAC per FD-02                                 | G15          |
| 6.5   | S7 / G16          | Staging UAT pack                               | UAT          |
| 6.6   | CUST-06 / VEND-07 | Events Phase-1 UX + supply                     | After N8N-02 |
| 6.7   | Scope-gated       | product_class/condition/evidence only if FD-06 | MR-S05/S06   |

**Exit:** Eligible for **GO real-money beta** only if `release-gates.md` Go/No-Go table says so.

---

## Parallelism rules

| Can run in parallel                                                | Must stay serial                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------- |
| Wave 0 decisions ‖ Wave 5 Sentry/uptime setup (no secrets in docs) | Wave 1 before claiming Wave 2 release drills meaningful |
| Panel localhost cleanup ‖ Wave 1                                   | Backup before Wave 3 migrates                           |
| Doc SoT banners (MR-L02) anytime                                   | Production `0056` after staging KYC PASS                |
| Search degraded diagnosis (API-07) anytime                         | `public_launch=true` only after full GO                 |

---

## Explicit out-of-wave (do not pull in)

- Seeding 75–100/840 vendors or fake GMV
- Building Django/Meilisearch/Celery/DPO/Yango API from superseded docs
- Vendor staff RBAC (OUT unless FD-10)
- City Guides / referrals / AR / multi-currency seam
- Auto-creating KYC records for orphaned demo vendors

---

## Definition of done for this consolidation track

Documentation track is done when these six files exist and match master tip `d5c2134`+ ancestry including #274/#289–#294:

1. `master-reconciliation-register.md`
2. `production-readiness-scorecard.md`
3. `panel-backlogs.md`
4. `release-gates.md`
5. `source-conflicts-and-decisions.md`
6. `implementation-wave-plan.md`

Engineering track is **not** done until staging/production gates PASS. CODE_COMPLETE ≠ ready.

---

## Suggested first coding pebbles (after this docs PR)

| Pebble                                   | Branch sketch                        | Owns                                          | Acceptance                       |
| ---------------------------------------- | ------------------------------------ | --------------------------------------------- | -------------------------------- |
| Staging money evidence pack              | `cursor/staging-prepaid-ledger-****` | API tests + ops runbook only (no prod enable) | S1–S3 checklist filled           |
| n8n release+tickets activate             | `cursor/n8n-release-tickets-****`    | `infra/n8n` + ops docs                        | Active workflows + execution IDs |
| Migration reconcile plan                 | `cursor/db-migrate-reconcile-****`   | migration notes + staging apply scripts/docs  | Drift CLOSED on staging          |
| Customer KYC badge + localhost residuals | `cursor/customer-kyc-localhost-****` | `apps/customer` only                          | CUST-13 + G2 residuals           |

---

_Do not flip production payment kill-switches or `public_launch` from these waves without the release evidence pack in `release-gates.md`._
