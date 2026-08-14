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
passed **integrated staging certification** and carries immutable evidence proving
that certification completed **before** the merge gate runs.

**Correct flow (evidence pre-exists validation):**

```text
candidate PR head frozen at SHA X
  → exact SHA X placed on staging
  → deploy-staging.yml succeeds
  → release-certify integrated-staging succeeds with result PASS
  → certification workflow uploads immutable artifact + digest
  → release/integration PR carries infra/merge-release-evidence.json for SHA X
  → merge gate validates evidence read-only (no SHA rebinding)
  → master merge allowed
```

**Forbidden flow (self-attesting — RELCTRL-02 blocks this):**

```text
PR opens
  → CI rewrites merge-release-evidence.json SHAs to PR head
  → merge gate validates rewritten JSON
  → merge allowed
  → staging certification happens later
```

Steps for runtime/schema PRs:

1. Deploy and certify on `staging` via `.github/workflows/deploy-staging.yml`.
2. Run `.github/workflows/release-certify.yml` in `integrated-staging` mode until
   certification completes with **`result: PASS`** (not
   `CERTIFIABLE_AFTER_INTEGRATION` or other non-terminal states).
3. Copy the certification artifact fields into
   `infra/merge-release-evidence.json` on the release PR to `master` (see
   `infra/merge-release-evidence.example.json` schema version `2`).
4. CI job **Merge release gate (RELCTRL-01/02)** validates the checked-in evidence
   **read-only** — it never creates, rewrites, or normalizes evidence. The working
   tree must remain unchanged across validation (`git diff --exit-code`).

Application/runtime changes require valid merge evidence. **Governance-only** PRs
that touch only `.github/**`, `scripts/ci/**`, `docs/**`, the merge/release
evidence **example** templates, or non-runtime tests under
`services/api/tests/**` may skip the gate (fail-closed scope detection in
`scripts/ci/detect_merge_evidence_scope.py`).

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
3. `scripts/qa/release-certify.sh --mode integrated-staging` must complete with
   **`PASS`** (completed certification — not `CERTIFIABLE_AFTER_INTEGRATION`).
4. Evidence is captured in `infra/merge-release-evidence.json` on the PR to
   `master` before merge, including distinct staging deploy and certification run
   ids plus artifact digest provenance (see
   `infra/merge-release-evidence.example.json`). Post-merge **release parity
   contract** evidence for Production verification remains separate (see
   `infra/release-evidence-contract.example.json`).

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
- `scripts/ci/validate_merge_release_evidence.py` — merge gate (read-only, PASS-only)
- `scripts/ci/detect_merge_evidence_scope.py` — governance-only exemption detector
- `scripts/ci/validate_release_parity.py` — post-merge verify parity gate
