# Ops drills evidence pack — 2026-07-20 (Prompt 10)

**Overall verdict: FAIL** (restore CONDITIONAL process demo only; rollback NOT_RUN; load NOT_RUN).

Do not declare G7 / G9 / load PASS. Thresholds were not altered after results.

| Drill                  | Verdict            | Notes                                                                                                                                                                                                                                                              |
| ---------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A. Restore             | **CONDITIONAL**    | Checksum-verified restore into isolated local Postgres; artifact is `backup_mode=drill` / `env_id=local-ci`, not an approved n8n/OCI production backup. Key catalogue/money tables absent in dump. API readiness vs restore NOT_RUN. Production never overwritten. |
| B. Deployment rollback | **FAIL / NOT_RUN** | Frontend SHAs + rollback candidates recorded. Controlled promote/rollback deliberately **not** executed (API digest UNKNOWN, API 502, migration tip drift).                                                                                                        |
| C. Load test @100cc    | **FAIL / NOT_RUN** | k6 harness offline-validated; live 100 VU run blocked (no k6 binary, no approved staging, API 502). Documented p95 targets unchanged.                                                                                                                              |
| D. Evidence pack       | **COMPLETE**       | This directory.                                                                                                                                                                                                                                                    |

---

## Preconditions

| Check                                            | Result          | Evidence                                                                                                                                    |
| ------------------------------------------------ | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Approved backup workflow imported + valid backup | **FAIL**        | `infra/n8n/backup.json` absent on master; n8n search `backup` → 0; only `backup-schedule.md` contract. Artifact used = local-ci drill dump. |
| Deployment SHAs known                            | **PARTIAL**     | Customer/vendor/admin prod SHAs in `versions.txt`.                                                                                          |
| API digest known                                 | **FAIL**        | `DEPLOYED_API_DIGEST=UNKNOWN`; `/healthz` `/readyz` `/fingerprint` → **502**.                                                               |
| Migration tip known                              | **YES (drift)** | Live tip `0063_revoke_execute_review_reply_guards` (≠ repo `0063` source_key semantics previously noted).                                   |
| `public_launch` false                            | **PASS**        | SQL confirmed false (recorded in `versions.txt`).                                                                                           |
| Sandbox/test fixtures                            | **PASS**        | Drill dump + offline k6/invariant checks only.                                                                                              |
| Rollback targets known                           | **PARTIAL**     | Vercel deployment IDs recorded; API immutable digest missing.                                                                               |

See `versions.txt`, `commands/executed.md`, `logs/preflight-refresh.txt`.

---

## A. Restore drill

### Method

1. Selected artifact: `/tmp/vergeo5-backups-ci/vergeo5-20260720T150434Z.sql.gz`
   - Manifest: `restore-verification/artifact-manifest.json`
   - `backup_mode=drill`, `env_id=local-ci`, `migration_tip=0099_test`
2. Checksum verified before restore:
   - expected/actual `26f5a8fd62f5858b35b2b6be1b2881f562e932a23b893929ce262c4459283b5c` → **match**
   - `restore-verification/checksum.txt`
3. Restored into **isolated non-production** local Postgres 16 DB `vergeo5_restore_drill_20260720152311` (then dropped).
4. Timestamps: start `2026-07-20T15:23:11Z`, finish `2026-07-20T15:23:11Z`, elapsed **0s**.
5. Verification (see `logs/restore-drill.txt`, `logs/restore-psql.out`, `restore-verification/checklist.md`):

| Check                                 | Result                                                         |
| ------------------------------------- | -------------------------------------------------------------- |
| Migration ledger                      | Tip `0099_test` only (drill schema)                            |
| Key table counts                      | products/listings/orders/payments/ledger/refunds = **MISSING** |
| Constraints / indexes                 | Minimal (1 index, 1 constraint sample on drill tables)         |
| RLS / FORCE RLS                       | Sample empty (no money/catalogue tables)                       |
| Representative catalogue              | **FAIL** — not present in dump                                 |
| Representative order/payment/ledger   | **FAIL** — not present                                         |
| API readiness against restored target | **NOT_RUN** (API targets Supabase cloud; local DB only)        |
| Production overwrite                  | **false**                                                      |

6. RTO: elapsed 0s ≤ documented **30-minute (1800s)** target numerically → **within target**, but **not** a production-artifact restore; gate remains non-PASS.
7. Production never overwritten.

**Restore gate contribution to G7:** CONDITIONAL process proof only → **G7 remains FAIL**.

---

## B. Deployment rollback drill

### Recorded versions (`versions.txt`)

| Surface       | Current / candidate                           |
| ------------- | --------------------------------------------- |
| master tip    | `d9839db349887ab48a52c18546e05961a62498d6`    |
| customer prod | `cde40bf…` / `dpl_6Pgevsi…` (prior `14af318`) |
| vendor prod   | `5a4668a…` / `dpl_3qg4H35…` (prior `1d137ae`) |
| admin prod    | `2f99711…` / `dpl_298135…` (prior `5a4668a`)  |
| API digest    | **UNKNOWN**                                   |

### Execution

| Step                                                       | Result                            |
| ---------------------------------------------------------- | --------------------------------- |
| Record SHAs                                                | Done                              |
| Deploy controlled harmless change                          | **NOT_RUN**                       |
| Verify new release                                         | **NOT_RUN**                       |
| Roll back customer/vendor/admin/API via immutable versions | **NOT_RUN**                       |
| Verify health + critical routes after rollback             | **NOT_RUN**                       |
| Elapsed time / failed steps                                | n/a — drill aborted before mutate |

**Rationale for abort:** mutating production frontends while API returns 502 and API digest is unknown would create an undefended rollback path and risk widening outage. Candidates preserved in `rollback-verification/candidates.md`.

**G9 remains FAIL.**

---

## C. Load test

### Harness

- Committed: `load/k6/checkout-load.js`, `load/k6/browse-load.js`, `load/invariant-check.py`
- Offline: `node --check` + `py_compile` **PASS** (`logs/load-offline-recheck.log`)
- Thresholds (unchanged after this drill):

| Metric                | Target   |
| --------------------- | -------- |
| Checkout 100cc p95    | `<500ms` |
| Browse search/plp p95 | `<400ms` |
| Browse suggest p95    | `<250ms` |
| HTTP failed rate      | `<0.01`  |

### Live 100 concurrent-user run

**NOT_RUN** — blockers:

1. `k6` binary absent in environment
2. No approved staging target with Lenco stub + seeded JWTs
3. Production API `/healthz` → 502 — refuse prod load and real provider charges

| Metric                           | Value       |
| -------------------------------- | ----------- |
| p50 / p95 / p99                  | n/a         |
| Throughput                       | n/a         |
| HTTP error rate                  | n/a         |
| Database errors                  | n/a         |
| Queue/workflow errors            | n/a         |
| Money/order invariants post-test | **NOT_RUN** |

See `metrics/load-summary.json`, `load-results/NOT_RUN.md`.

**Load gate / LIVE-11 remains FAIL.** Thresholds were **not** relaxed.

---

## D. Evidence inventory

```text
ops-drills/
  README.md                          ← this report + gate verdicts
  versions.txt
  commands/executed.md
  logs/
    preflight-refresh.log
    restore-drill.log
    restore-psql.out
    load-offline-validation.log
    load-offline-recheck.log
  restore-verification/
    artifact-manifest.json
    checksum.txt
    checklist.md
  rollback-verification/
    candidates.md
    NOT_RUN.md
  load-results/
    NOT_RUN.md
  metrics/
    load-summary.json
  screenshots/
    README.md                        ← none (CLI/API only; API 502)
  defects.md
```

---

## Defects discovered

See `defects.md`. Headline blockers: missing approved backup workflow/artifact; API 502 / unknown digest; no staging for 100cc; k6 absent.

---

## Final gate verdicts (Prompt 10 scope)

| Gate / item                       | Verdict                     | Evidence                                                            |
| --------------------------------- | --------------------------- | ------------------------------------------------------------------- |
| G7 Backups and restore proof      | **FAIL**                    | No approved scheduled backup artifact; CONDITIONAL local drill only |
| G9 Deployment / rollback evidence | **FAIL**                    | SHAs partial; API digest unknown; rollback drill NOT_RUN            |
| LIVE-09 restore ≤30min            | **FAIL** / CONDITIONAL demo | Numerically fast on drill dump; not production DR proof             |
| LIVE-10 rollback drill            | **FAIL**                    | NOT_RUN                                                             |
| LIVE-11 load p95 @100cc           | **FAIL**                    | NOT_RUN; thresholds unchanged                                       |
| `public_launch`                   | remains **false**           | Not flipped                                                         |

**Go/no-go contribution:** NO-GO for real money and public launch — G7 and G9 remain FAIL.
