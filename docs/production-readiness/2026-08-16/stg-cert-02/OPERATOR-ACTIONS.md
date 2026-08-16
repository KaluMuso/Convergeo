# STG-CERT-02 — operator actions required

**Candidate SHA:** `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c`  
**Verdict at evidence capture:** `OPERATOR_ACTION_REQUIRED`  
**Production:** do not modify · **`public_launch` must remain false**

## Why certification is blocked

1. **Concurrency lock** — stale deploy-staging run [#30897217202](https://github.com/KaluMuso/Convergeo/actions/runs/30897217202) (SHA `b084b0de…`, since 2026-08-04) holds the `deploy-staging` concurrency group with `cancel-in-progress: false`.
2. **Candidate run queued** — push run [#31937277741](https://github.com/KaluMuso/Convergeo/actions/runs/31937277741) (correct SHA `9a08540d…`) is `pending` with **zero jobs** and **empty** `pending_deployments` until the lock clears.
3. **Cloud agent permissions** — integration token cannot cancel runs, approve environment deployments, or `workflow_dispatch` release-certify (all HTTP 403).

## Step 1 — Clear the concurrency blocker

In GitHub Actions UI (or with a token that has `actions: write`):

1. Open [run #30897217202](https://github.com/KaluMuso/Convergeo/actions/runs/30897217202).
2. **Cancel workflow** (do **not** approve — it targets wrong SHA `b084b0dec74d7f3871c7f857186ad76cc65d3d4c`).

Do **not** force-push `master`. Do **not** create a new application commit on `staging`.

## Step 2 — Let candidate deploy-staging proceed (PUSH certifiable)

After cancel, run [#31937277741](https://github.com/KaluMuso/Convergeo/actions/runs/31937277741) should schedule jobs. If it remains stuck, cancel it and re-push the **same** SHA to `staging`:

```bash
git push origin 9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c:staging
```

(Only if GitHub accepts a no-op ref update; otherwise use repository settings to re-run after blocker cancel.)

When the **Environment separation** job reaches `waiting`:

1. Open the **candidate** deploy run (must be `event=push`, `head_sha=9a08540d…`).
2. Click **Review deployments** → approve **staging** environment (reviewer: **KaluMuso**).

**Forbidden for certification evidence:**

- `workflow_dispatch` deploy-staging
- `skip_vercel` / `skip_migrate` inputs
- Any staging branch SHA other than `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c`

## Step 3 — Confirm deploy proof (RELCTRL-04)

Successful push deploy must upload artifact **`staging-sha-proof`** proving:

| Field                        | Required value                             |
| ---------------------------- | ------------------------------------------ |
| STAGING_BRANCH_SHA           | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` |
| MIGRATION_RESULT             | `success`                                  |
| API fingerprint `git_sha`    | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` |
| API fingerprint Supabase ref | `iyasmrmbcrvlfxpzescb`                     |
| Customer Preview SHA         | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` |
| Vendor Preview SHA           | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` |
| Admin Preview SHA            | `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c` |

## Step 4 — Dispatch integrated staging certification

From **`staging` ref** (not `master`):

```bash
gh workflow run release-certify.yml \
  --ref staging \
  -f mode=integrated-staging \
  -f candidate_sha=9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c
```

Require terminal **PASS** and artifact **`staging-certification-evidence`**.

## Step 5 — Update evidence

After PASS, append deploy run id, portal SHAs, certify run id, and set `FINAL_STAGING_CERTIFICATION=PASS` in `EXECUTION-REPORT.md`.
