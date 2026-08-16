# STG-CERT-02 execution report — 2026-08-16

**Operator:** Cursor Cloud Agent (STG-CERT-02)  
**Candidate SHA:** `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c`  
**Staging branch SHA:** `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` (verified via `origin/staging`)  
**Staging DB tip (pre-cert):** `20260815230000` on `iyasmrmbcrvlfxpzescb` (STG-LEDGER-02 complete)  
**Production touched:** **NO** · **`public_launch`:** **false**

## Phase summary

| Phase                             | Result               | Notes                                                                       |
| --------------------------------- | -------------------- | --------------------------------------------------------------------------- |
| A — Diagnose zero-job pending run | **PASS (diagnosis)** | Root cause: **CONCURRENCY_BLOCK** — see `PHASE-A-DIAGNOSIS.json`            |
| B — Recover staging deploy        | **BLOCKED**          | Agent HTTP 403 on cancel/approve; operator must clear run #30897217202      |
| C — Deploy proof                  | **PENDING**          | Live API still on pre-candidate SHA `161b58a3…`; no `staging-sha-proof` yet |
| D — Release certification         | **BLOCKED**          | Agent HTTP 403 on `workflow_dispatch` release-certify                       |
| E — Evidence                      | **PASS (interim)**   | This report + operator checklist                                            |

## Phase A — Zero jobs on run #31937277741

| Field               | Value                                                                          |
| ------------------- | ------------------------------------------------------------------------------ |
| Run                 | [#31937277741](https://github.com/KaluMuso/Convergeo/actions/runs/31937277741) |
| status              | `pending`                                                                      |
| conclusion          | _(null)_                                                                       |
| event               | `push`                                                                         |
| head_sha            | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c`                                     |
| run_attempt         | 1                                                                              |
| jobs                | **[]** (total_count 0)                                                         |
| pending_deployments | **[]**                                                                         |
| **Classification**  | **CONCURRENCY_BLOCK**                                                          |

**Mechanism:** `.github/workflows/deploy-staging.yml` sets `concurrency.group: deploy-staging` with `cancel-in-progress: false`. Stale run [#30897217202](https://github.com/KaluMuso/Convergeo/actions/runs/30897217202) (`status=waiting`, wrong SHA `b084b0de…`, job **Environment separation** waiting since 2026-08-04) holds the group. Run #31937277741 cannot materialize jobs until that run completes or is cancelled.

**Not environment approval on #31937277741:** `GET …/pending_deployments` for run 31937277741 returned `[]`. Pending approval exists only on blocker run #30897217202 (`reviewer: KaluMuso`, `current_user_can_approve: false` for cloud token).

**Workflow validation:** `deploy-staging.yml` and `release-certify.yml` YAML parse OK; workflow state `active`.

## Phase B — Recovery attempts (agent)

| Action                                                  | Result   |
| ------------------------------------------------------- | -------- |
| `gh run cancel 30897217202`                             | HTTP 403 |
| `gh run cancel 31937277741`                             | HTTP 403 |
| Approve pending deployment API                          | HTTP 403 |
| Re-push same SHA (not attempted — blocked until cancel) | N/A      |

**Operator recovery (RELCTRL-04 compliant):** Cancel #30897217202 → allow #31937277741 to schedule → approve **staging** environment on the **candidate** push run only. Do not use `workflow_dispatch`, `skip_vercel`, or `skip_migrate`.

## Phase C — Pre-deploy live target baseline

Probed at evidence capture (deploy for candidate **not** complete):

| Probe                                             | Result                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------ |
| `GET https://api.staging.vergeo5.com/healthz`     | `{"status":"ok"}`                                                              |
| `GET https://api.staging.vergeo5.com/readyz`      | ok (search_embedding degraded)                                                 |
| `GET https://api.staging.vergeo5.com/fingerprint` | `git_sha=161b58a3…` ≠ candidate; `supabase_project_ref=iyasmrmbcrvlfxpzescb` ✓ |
| Vercel staging-branch previews                    | `DEPLOYMENT_NOT_FOUND`                                                         |

Snapshots: `pre-deploy-*.json` in this directory.

**Post-deploy E2E probes** (catalogue, search, PDP, cart, checkout honesty, private-event chain, GMV reservation) — **PENDING** successful deploy-staging PASS.

## Phase D — Release certification

`gh workflow run release-certify.yml --ref staging -f mode=integrated-staging -f candidate_sha=9a08540d…` → **HTTP 403** (integration lacks `actions: write` / workflow dispatch).

Operator must dispatch from **`staging` ref** after deploy PASS. See `OPERATOR-ACTIONS.md`.

## Certification evidence fields (interim)

```
STAGING_DEPLOY_RUN_ID = 31937277741 (pending; not certifiable until success)
STAGING_DEPLOY_CAUSE_OF_PREVIOUS_PENDING = CONCURRENCY_BLOCK (blocker: 30897217202 ENVIRONMENT_APPROVAL on wrong SHA)
STAGING_API_SHA = 161b58a3e1973b79abd4fc8064611c50fa0268c8 (pre-deploy; want 9a08540d…)
STAGING_CUSTOMER_SHA = (not deployed — Vercel DEPLOYMENT_NOT_FOUND)
STAGING_VENDOR_SHA = (not deployed)
STAGING_ADMIN_SHA = (not deployed)
STAGING_DB_TIP = 20260815230000
STAGING_SHA_PROOF = (artifact not produced)
RELEASE_CERTIFY_RUN_ID = (not dispatched)
STAGING_CERTIFICATION_EVIDENCE = (artifact not produced)
DEPLOYED_TARGET_E2E = PENDING
FINAL_STAGING_CERTIFICATION = OPERATOR_ACTION_REQUIRED
```

## Next operator checklist

See **`OPERATOR-ACTIONS.md`** for ordered steps: cancel #30897217202 → approve candidate deploy → verify `staging-sha-proof` → dispatch release-certify → update this report to **PASS**.
