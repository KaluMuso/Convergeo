# Production release control (RELCTRL-01)

Canonical contract for how Vergeo5 frontends reach Production without
`master` merges auto-promoting live customer traffic.

## Branch topology

```text
feature/* / cursor/* / agent/*
        ↓
      master          ← integration; full CI + Performance; Vercel Preview only
        ↓
      staging         ← exact-SHA staging candidate; staging API + Supabase proof
        ↓
    production        ← release-only; sole Git branch for Vercel Production deploys
```

| Branch       | Purpose                                     | Vercel effect                                                      | API / DB                                                                |
| ------------ | ------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `master`     | Integration, CI gates, Performance          | **Preview** deployments only (must not replace Production domains) | None                                                                    |
| `staging`    | Certified staging candidate at an exact SHA | **Preview** on branch `staging` (per-project Preview env vars)     | Staging API + staging Supabase via `deploy-staging.yml`                 |
| `production` | Certified Production frontend release       | **Production** deployments for customer, vendor, admin             | No automatic API/DB migration — parity evidence required before advance |

## Vercel Production Branch contract

For each Vercel project (`convergeo-customer`, `convergeo-vendor`, `convergeo-admin`):

| Setting               | Required value                                                       |
| --------------------- | -------------------------------------------------------------------- |
| Git integration       | Enabled (Preview preserved)                                          |
| **Production Branch** | `production` (not `master`)                                          |
| Production domains    | Unchanged (`vergeo5.com`, `vendor.vergeo5.com`, `admin.vergeo5.com`) |

`master` pushes must create Preview deployments only. Only fast-forwards of
`production` may replace Production domains via Git integration.

Operator cutover (one-time per project): Vercel → Project → Settings → Git →
**Production Branch** → change `master` → `production` → Save.

## Exact-SHA staging certification

Before any Production frontend promotion:

1. `staging` (or a pinned SHA) is deployed via `.github/workflows/deploy-staging.yml`.
2. Staging API fingerprint, Supabase migration replay, and Vercel Preview proofs
   match the **same** `candidate_sha`.
3. `scripts/qa/release-certify.sh --mode integrated-staging` (or equivalent
   evidence) records `CERTIFIABLE_AFTER_INTEGRATION` or stricter pass.
4. Evidence is captured in a **release parity contract** JSON (see
   `infra/release-evidence-contract.example.json`).

Promotion without staging certification is **fail-closed**.

## Frontend / API / database parity

Production frontend promotion does **not** deploy the API or migrate Production
Supabase. The parity contract must therefore prove:

| Field                            | Meaning                                                        |
| -------------------------------- | -------------------------------------------------------------- |
| `candidate_frontend_sha`         | Git SHA to fast-forward `production` to                        |
| `candidate_api_sha`              | API image / fingerprint SHA the frontend expects in Production |
| `required_db_migration_baseline` | Minimum Production DB migration version (filename prefix)      |
| `production_db_evidence_run_id`  | Run id from `capture-production-db-evidence.yml`               |
| `staging_certification`          | Staging proof bundle referencing the same frontend SHA         |
| `production_api_sha_observed`    | Cross-checked live against `GET /fingerprint` during promotion |

**Production DB trust model (fail-closed):**

1. Run `capture-production-db-evidence.yml` for the same `candidate_sha` using
   `PRODUCTION_READONLY_DB_URL` (read-only). Artifact: `production-db-migration-evidence`.
2. Promotion downloads that artifact by `production_db_evidence_run_id`, verifies
   the GitHub run succeeded, and re-queries the live read-only DB — live
   `max(version)` must **exactly match** artifact `migration_head`.
3. Manual `production_db_migration_head_observed` JSON claims are **not** accepted.

The promotion workflow (`promote-production-frontends.yml`) refuses when:

- staging certification is absent or references a different SHA;
- Production API fingerprint is behind `candidate_api_sha`;
- DB evidence is missing, unproven, or live head diverges from artifact;
- CI or Performance checks are not green on `candidate_frontend_sha`.

**Current certified frontend SHA (2026-08-13):** `0620de7d8a938d3cebf2ee64468113a219ff6c42`

**Current Production API SHA:** `2d549bb3a5213597d3c32e497e6814b50ad7ac18`

**Current Production DB head:** `0071_vendor_listing_compare_at`

Frontend-at-master parity with all three Vercel Production apps does **not**
imply coordinated full-stack release eligibility while API/DB skew remains.

## Production promotion (explicit)

Use **Actions → Promote production frontends** (`.github/workflows/promote-production-frontends.yml`):

1. Run **Capture production DB evidence** for the same `candidate_sha`; note the run id.
2. Input `candidate_sha` (40-char git SHA on `master`).
3. Attach `release_evidence_path` pointing to a validated parity contract JSON
   including `production_db_evidence_run_id`.
4. Workflow runs in GitHub Environment `production` (founder approval).
5. Fast-forwards `production` only (never force-push).
6. Waits for Vercel Production READY on all three projects at the exact SHA.
7. Runs read-only deployment-plane verification and uploads evidence artifact.

**Emergency / break-glass:** `skip_vercel_wait` and `skip_live_verify` are accepted
only when `emergency_confirm` is exactly `I_ACCEPT_DEGRADED_PRODUCTION_EVIDENCE`.
Normal releases must leave both skips **false**. Degraded runs record
`verdict=degraded` in the release evidence artifact.

Legacy `.github/workflows/deploy-production.yml` remains for coordinated API +
manual Vercel promote; it does **not** auto-run on push.

## Rollback

1. Identify last known-good `production` SHA (deployment evidence / health `buildId`).
2. Re-run **Promote production frontends** with that SHA **only if** parity
   evidence still valid; otherwise roll back API/DB first per `infra/ROLLBACK.md`.
3. Emergency: Vercel Dashboard → Deployments → Promote previous Production
   deployment (records operator action; restore `production` branch to match).

## Emergency release path

1. Fix on `master` → CI green → staging certification at exact SHA.
2. Parity contract updated with observed Production API/DB heads.
3. `promote-production-frontends` with founder `production` environment approval.
4. Post-deploy `scripts/ops/verify_live.sh` + evidence artifact retained 90 days.

## Who may advance `production`

- GitHub Environment `production` approvers (founder / release operators).
- The promotion workflow service account (`GITHUB_TOKEN` with `contents: write`).
- Direct git pushes to `production` should be blocked by branch protection.

## Branch protection (operator-required)

GitHub API access from automation cannot configure branch protection. Apply
these settings in **Settings → Branches → Branch protection rules** for
`production`:

| Control               | Setting                                               |
| --------------------- | ----------------------------------------------------- |
| Branch name pattern   | `production`                                          |
| Restrict pushes       | Enabled — limit to release operators / GitHub Actions |
| Allow force pushes    | **Disabled**                                          |
| Allow deletions       | **Disabled**                                          |
| Require pull request  | Optional (promotion is workflow-driven fast-forward)  |
| Require status checks | Optional — promotion workflow verifies CI externally  |
| Require deployments   | Optional — tie to `production` environment            |

The `promote-production-frontends` workflow must retain permission to fast-forward
`production` without force-push.

## Regression prevention

CI job **Release control contract (RELCTRL-01)** runs
`scripts/ci/test-release-control-contract.sh` on every PR/push. It fails if
docs or workflows reintroduce `master` as the Vercel Production Branch or omit
required governance files.

## Related

- `infra/vercel.md` — Vercel project settings
- `infra/ENVIRONMENTS.md` — deployment planes
- `.github/workflows/deploy-staging.yml` — staging pipeline (no Production promotion)
- `.github/workflows/deploy-production.yml` — legacy API + manual Vercel promote
- `scripts/ci/validate_release_parity.py` — parity gate implementation
