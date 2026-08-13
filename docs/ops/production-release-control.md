# Production release control (RELCTRL-01)

Canonical contract for how Vergeo5 frontends reach Production via **protected
`master`**. Merges into `master` are release events; Vercel Production Branch
is `master`.

## Branch topology

```text
feature/* / cursor/* / agent/*
        ↓
   PR / integration work
        ↓
      staging
        ↓
 exact-SHA staging certification
        ↓
      master          ← protected; Vercel Production Branch
        ↓
 Vercel Production (customer, vendor, admin)
```

| Branch    | Purpose                                     | Vercel effect                              |
| --------- | ------------------------------------------- | ------------------------------------------ |
| `staging` | Certified staging candidate at an exact SHA | **Preview** on branch `staging`            |
| `master`  | Production-facing integration / release     | **Production** for customer, vendor, admin |

**Deprecated:** the historical `production` Git branch may still exist on the
remote but is **unused** for release promotion. Do not fast-forward or delete
it in routine operations. Release truth is `master`.

## Merge-to-master gate

A PR must **not** merge into `master` unless the exact PR head SHA has already
passed **staging certification** and required release gates.

1. Deploy and certify on `staging` via `.github/workflows/deploy-staging.yml`.
2. Record integrated-staging evidence (`CERTIFIABLE_AFTER_INTEGRATION` or stricter).
3. Open the release/integration PR to `master` carrying
   `infra/merge-release-evidence.json` binding the PR head SHA to that
   certification (see `infra/merge-release-evidence.example.json`).
4. CI job **Merge release gate (RELCTRL-01)** validates the evidence offline —
   no Production DB credentials on ordinary feature PRs.

Application changes (`apps/`, `services/`, `packages/`, `supabase/migrations/`)
require valid merge evidence. Governance-only PRs (docs, CI scripts, workflow
metadata) may skip the gate.

## Vercel Production Branch contract

For each Vercel project (`convergeo-customer`, `convergeo-vendor`,
`convergeo-admin`):

| Setting               | Required value                                                       |
| --------------------- | -------------------------------------------------------------------- |
| Git integration       | Enabled (Preview preserved)                                          |
| **Production Branch** | **`master`**                                                         |
| Production domains    | Unchanged (`vergeo5.com`, `vendor.vergeo5.com`, `admin.vergeo5.com`) |

Non-`master` branches (including `staging` and PR previews) create Preview
deployments only.

## Exact-SHA staging certification

Before merging to `master`:

1. `staging` is deployed via `.github/workflows/deploy-staging.yml`.
2. Staging API fingerprint, Supabase migration replay, and Vercel Preview proofs
   match the **same** `candidate_sha`.
3. `scripts/qa/release-certify.sh --mode integrated-staging` records
   `CERTIFIABLE_AFTER_INTEGRATION` or stricter pass.
4. Evidence is captured in `infra/merge-release-evidence.json` on the PR to
   `master`, and in the post-merge **release parity contract** for Production
   verification (see `infra/release-evidence-contract.example.json`).

## Frontend / API / database parity

Merging to `master` deploys frontends via Vercel Git integration. The **verify**
workflow (`promote-production-frontends.yml`, read-only) proves live Production
after merge:

| Field                            | Meaning                                                     |
| -------------------------------- | ----------------------------------------------------------- |
| `candidate_frontend_sha`         | Must equal current `master` tip                             |
| `candidate_api_sha`              | API fingerprint SHA the frontend expects in Production      |
| `required_db_migration_baseline` | Minimum Production DB migration version                     |
| `production_db_evidence_run_id`  | Run id from `capture-production-db-evidence.yml`            |
| `staging_certification`          | Staging proof bundle for the same SHA                       |
| `production_api_sha_observed`    | Cross-checked live against `GET /fingerprint` during verify |

**Production DB trust model (fail-closed):**

1. Run `capture-production-db-evidence.yml` for the same `candidate_sha` using
   `PRODUCTION_READONLY_DB_URL` (read-only).
2. Verify workflow downloads that artifact, validates GitHub run provenance, and
   re-queries the live read-only DB — live `max(version)` must **exactly match**
   artifact `migration_head`.
3. Manual JSON claims are **not** accepted.

## Production verification (explicit, no ref moves)

Use **Actions → Verify production frontends**
(`.github/workflows/promote-production-frontends.yml`):

1. Merge staging-certified SHA into `master` (Vercel Production deploys from Git).
2. Run **Capture production DB evidence** for the same SHA; note the run id.
3. Dispatch verify with `candidate_sha` equal to **current master tip**.
4. Workflow runs in GitHub Environment `production` (founder approval).
5. **Does not** `git push` or move any branch ref.
6. Proves Vercel Production READY on all three apps at the master SHA.
7. Runs `verify_live.sh` and uploads evidence artifact.

**Emergency / break-glass:** `skip_vercel_wait` and `skip_live_verify` require
`emergency_confirm=I_ACCEPT_DEGRADED_PRODUCTION_EVIDENCE`.

Legacy `.github/workflows/deploy-production.yml` remains for coordinated API
redeploy; it does **not** auto-run on push.

## Rollback

1. Identify last known-good `master` SHA (deployment evidence / health `buildId`).
2. Revert or forward-fix on `master` per `infra/ROLLBACK.md` with full parity
   evidence before merge.
3. Emergency: Vercel Dashboard → promote previous Production deployment; align
   `master` via a controlled revert PR.

## Branch protection (operator-required)

Apply branch protection on **`master`** (not the deprecated `production` branch):

| Control               | Setting                                    |
| --------------------- | ------------------------------------------ |
| Require pull request  | Enabled                                    |
| Require status checks | CI, Performance, Merge release gate        |
| Allow force pushes    | **Disabled**                               |
| Require approvals     | Founder / release operators for production |

## Regression prevention

CI job **Release control contract (RELCTRL-01)** runs
`scripts/ci/test-release-control-contract.sh`. It fails if docs or workflows
reintroduce a separate `production` release branch or omit required governance
files.

## Related

- `infra/vercel.md` — Vercel project settings
- `infra/ENVIRONMENTS.md` — deployment planes
- `.github/workflows/deploy-staging.yml` — staging pipeline
- `.github/workflows/deploy-production.yml` — legacy API redeploy
- `scripts/ci/validate_merge_release_evidence.py` — merge gate
- `scripts/ci/validate_release_parity.py` — post-merge verify parity gate
