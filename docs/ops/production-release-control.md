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

A runtime/schema PR must **not** merge into `master` unless the exact PR head SHA
has already passed **integrated staging certification** recorded as an immutable
GitHub Actions artifact. The candidate tree must **not** gain a post-certification
commit (RELCTRL-03 eliminates the SHA deadlock from checked-in JSON).

**Correct flow (artifact-native — RELCTRL-03 + RELCTRL-04 full staging proof):**

```text
candidate PR head frozen at SHA X (no further commits on candidate branch)
  → staging branch points to exact SHA X
  → deploy-staging.yml push run succeeds for SHA X (NOT workflow_dispatch)
  → deploy run uploads staging-sha-proof artifact (3 portals + API fingerprint + migrate success)
  → release-certify.yml dispatched FROM staging ref at SHA X (candidate_sha=X)
  → emitter downloads staging-sha-proof; derives staging-certification-evidence from proof
  → merge gate queries GitHub Actions for completed certification at SHA X
  → gate downloads both artifacts, validates provenance chain, verifies certifiable deploy run
  → master merge allowed (candidate tree unchanged)
```

**Provenance chain (RELCTRL-04 release invariant):**

```text
PR head SHA X
  == staging Git branch SHA X
  == deploy-staging push head_sha X
  == staging-sha-proof candidate X
  == Customer / Vendor / Admin Preview SHA X
  == staging API fingerprint git_sha X
  == release-certify head_sha X (from staging ref)
  == staging-certification-evidence candidate X
```

**Forbidden flows:**

```text
PR opens → CI rewrites merge-release-evidence.json → merge allowed (RELCTRL-02 blocked)

certify SHA X → commit evidence JSON on candidate → new head SHA Y invalidates X (RELCTRL-03 blocked)

deploy-staging workflow_dispatch with skip_vercel / skip_migrate → not certifiable (RELCTRL-04)

certification emitter reconstructs portal/API SHAs from candidate alone → blocked (RELCTRL-04)

ordinary CI run masquerades as staging certification (blocked)
```

Steps for runtime/schema PRs:

1. Push exact candidate SHA to `staging` (triggers `.github/workflows/deploy-staging.yml`
   on `push` — manual `workflow_dispatch` deploys are operational only, not certifiable).
2. Confirm the deploy run uploaded artifact `staging-sha-proof` with all three portal
   preview SHAs, API fingerprint, and `migrate_supabase_result=success`.
3. Dispatch `.github/workflows/release-certify.yml` **from the `staging` branch ref**
   with `mode=integrated-staging` and `candidate_sha=<exact PR head>` until verdict
   is **`PASS`**.
4. Confirm artifact `staging-certification-evidence` exists on the successful
   certification workflow run (see `infra/staging-certification-evidence.example.json`).
5. Open/update the PR to `master` **without** adding post-certification commits.
6. CI job **Merge release gate** calls `verify_staging_certification_gate.py`
   (read-only; `git diff --exit-code`).

Application/runtime changes require artifact certification. **Governance-only** PRs
that touch only `.github/**`, `scripts/ci/**`, `scripts/qa/**`, `docs/**`, evidence
**example** templates, or non-runtime tests under `services/api/tests/**` may skip
the gate (fail-closed scope detection in `scripts/ci/detect_merge_evidence_scope.py`).

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

1. `staging` is deployed via `.github/workflows/deploy-staging.yml` **push** event
   (full pipeline; no `skip_vercel` / `skip_migrate`).
2. Deploy run must upload `staging-sha-proof` — customer, vendor, and admin preview
   SHAs plus API fingerprint must all resolve to the **same** `candidate_sha`;
   `migrate_supabase_result` must be **`success`** (skipped migrations are not
   certifiable).
3. `scripts/qa/release-certify.sh --mode integrated-staging` (via
   `.github/workflows/release-certify.yml` dispatched from **`staging` ref** with
   explicit `candidate_sha`) must complete with terminal verdict **`PASS`**.
4. Emitter `emit_staging_certification_evidence.py` derives
   `staging-certification-evidence` from verified `staging-sha-proof` values — never
   from candidate identity alone.
5. Immutable artifact `staging-certification-evidence` is uploaded by the
   certification workflow — **not** checked into the candidate PR. Post-merge
   **release parity contract** evidence for Production verification remains
   separate (see `infra/release-evidence-contract.example.json`).

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
- `scripts/ci/verify_staging_certification_gate.py` — artifact-native merge gate
- `scripts/ci/staging_deploy_provenance.py` — certifiable deploy run + staging-sha-proof
- `scripts/ci/emit_staging_certification_evidence.py` — certification artifact emitter
- `scripts/ci/validate_merge_release_evidence.py` — legacy checked-in JSON validator (regression tests only)
- `scripts/ci/detect_merge_evidence_scope.py` — governance-only exemption detector
- `scripts/ci/validate_release_parity.py` — post-merge verify parity gate
