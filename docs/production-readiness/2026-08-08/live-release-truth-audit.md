# Live release truth audit — 2026-08-08

Evidence gathered from GitHub API, Supabase MCP, Vercel MCP, and live HTTP probes.
No production mutations performed.

## Historical → current truth deltas

| Historical finding                                    | Current truth                                                                                                                       |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `origin/master` at `ce007170`                         | **MOVED** — tip is `5b9556c96f774a74af60a6eda7a56130daceb6cb` (+1 favicon commit)                                                   |
| Production DB at `0071`                               | **CONFIRMED** — `dpadrlxukcjbewpqympu` tip `0071_vendor_listing_compare_at` (70 ledger rows; timestamp-prefixed versions for 0051+) |
| Staging DB caught up through `0095` + RLS remediation | **CONFIRMED** — `iyasmrmbcrvlfxpzescb` tip `20260802153539_rls_policy_contract_remediation` (96 migrations, matches repo)           |
| RLS CI `continue-on-error` false-green risk           | **RESOLVED** — `rls` job step is blocking (no `continue-on-error`); only `Seed demo data` is soft-fail                              |
| Vercel rate limits blocking deploys                   | **CONFIRMED** — vendor/admin `5b9556c9` production builds `CANCELED` while customer `READY`                                         |
| No real-money transactions                            | **CONFIRMED** — production `payouts` count = 0 (payments/orders not queried in combined result; zero payout posture)                |
| Staging API fingerprint stale                         | **CONFIRMED WORSE** — `git_sha=161b58a3` (Aug 2); ~40+ commits behind master                                                        |
| `deploy-staging` pipeline healthy                     | **REGRESSED** — run `30897217202` stuck `waiting` on environment approval for 107h+                                                 |

## A. Current master

| Field                   | Value                                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------- |
| SHA                     | `5b9556c96f774a74af60a6eda7a56130daceb6cb`                                                                    |
| Message                 | Add files via upload (`apps/customer/public/Vergeo5.ico`)                                                     |
| Moved since `ce007170`? | **Yes** (+1 commit)                                                                                           |
| CI run (push)           | `31279029410` — in progress at audit time; JS/migrations/db/typegen/COD smoke green; RLS + Python API pending |

## B. Release identity matrix

| Surface             | Git SHA (target) | Deployed SHA                               | DB migration tip                                     | Environment                         | Status                                                                 |
| ------------------- | ---------------- | ------------------------------------------ | ---------------------------------------------------- | ----------------------------------- | ---------------------------------------------------------------------- |
| Customer staging    | `5b9556c9`       | **UNKNOWN** (no Preview proof at master)   | `20260802153539`                                     | staging                             | **FAIL** — no proven Preview; `staging.vergeo5.com` DNS absent         |
| Vendor staging      | `5b9556c9`       | **UNKNOWN**                                | `20260802153539`                                     | staging                             | **FAIL**                                                               |
| Admin staging       | `5b9556c9`       | **UNKNOWN**                                | `20260802153539`                                     | staging                             | **FAIL**                                                               |
| API staging         | `5b9556c9`       | `161b58a3e1973b79abd4fc8064611c50fa0268c8` | `20260802153539`                                     | staging (`iyasmrmbcrvlfxpzescb`)    | **FAIL** — API/DB skew; fingerprint `env=staging` ✓                    |
| Staging Supabase    | N/A              | N/A                                        | `20260802153539` / `rls_policy_contract_remediation` | staging                             | **PASS** — at repo tip                                                 |
| Production customer | `5b9556c9`       | `5b9556c96f774a74af60a6eda7a56130daceb6cb` | `0071`                                               | production                          | **PARTIAL** — frontend at tip; DB 25 migrations behind repo            |
| Production vendor   | `5b9556c9`       | `4cede31ebfc45fc810aff0c7a029a2d1256f76d3` | `0071`                                               | production                          | **FAIL** — SHA skew (rate-limit canceled `5b9556c9` build)             |
| Production admin    | `5b9556c9`       | `4cede31ebfc45fc810aff0c7a029a2d1256f76d3` | `0071`                                               | production                          | **FAIL** — SHA skew                                                    |
| Production API      | `5b9556c9`       | `68b941dc0895f40dcf56904f2072c65bd0eb9ebb` | `0071`                                               | production (`dpadrlxukcjbewpqympu`) | **FAIL** — API 5 commits behind customer; DB 25 migrations behind repo |
| Production Supabase | N/A              | N/A                                        | `0071_vendor_listing_compare_at`                     | production                          | **FAIL** — 25 migrations behind repo                                   |

### Live fingerprint probes

```json
// GET https://api.staging.vergeo5.com/fingerprint
{"status":"ok","env":"staging","git_sha":"161b58a3e1973b79abd4fc8064611c50fa0268c8","image_tag":"161b58a3e1973b79abd4fc8064611c50fa0268c8","supabase_project_ref":"iyasmrmbcrvlfxpzescb"}

// GET https://api.vergeo5.com/fingerprint
{"status":"ok","env":"production","git_sha":"68b941dc0895f40dcf56904f2072c65bd0eb9ebb","image_tag":"68b941dc0895f40dcf56904f2072c65bd0eb9ebb","supabase_project_ref":"dpadrlxukcjbewpqympu"}

// GET https://vergeo5.com/en/health
{"status":"ok","app":"customer","env":"production","buildId":"5b9556c96f774a74af60a6eda7a56130daceb6cb"}
```

## C. Database ledger comparison

| Ledger                              | Count | Tip                                              | vs repo (96 files) |
| ----------------------------------- | ----: | ------------------------------------------------ | ------------------ |
| Repository                          |    96 | `20260802153539_rls_policy_contract_remediation` | —                  |
| Staging (`iyasmrmbcrvlfxpzescb`)    |    96 | `20260802153539`                                 | **MATCH**          |
| Production (`dpadrlxukcjbewpqympu`) |    70 | `0071_vendor_listing_compare_at`                 | **25 MISSING**     |

Production missing migrations: `0072`–`0095` + `20260802153539_rls_policy_contract_remediation`.

Production uses timestamp-prefixed versions for migrations 0051–0071 (historical rename/reapply). Staging uses canonical numeric versions — content-equivalent, not a drift defect.

No duplicate versions or repo-only orphans on staging. No remote-only migrations beyond historical production timestamp aliases.

## D. Feature flags (live)

**Staging** — all launch-risk flags **disabled**: `public_launch`, `clips`, `clips_comments`, `waha_vendor_intake`, `paid_tiers`, `wallet`, `zamtel_collections`, `abandoned_cart`.

**Production** — subset (pre-0072 schema): same safe defaults on overlapping flags; `clips` / `waha_vendor_intake` rows absent (migrations not applied).

## E. RLS verdict

**PASS (CI configuration)** with evidence:

1. `vergeo_rls_tester` provisioned as `NOSUPERUSER NOBYPASSRLS` (`scripts/ci/provision-rls-tester.sql`, `services/api/tests/rls/conftest.py`).
2. RLS pytest step is **blocking** — `continue-on-error` removed (comment cites R02 / 2026-08-01).
3. Matrix covers cart/order, RFQ, follows/saves, analytics, clips, intake, commission immutability, launch tables (`tests/rls/test_*.py`).
4. `scripts/ci/test-staging-guards.sh` — 21 passed regression cases for proof validation.

**Note:** Nightly scheduled CI `31237768458` failed on `deps-audit` (GHSA-2v37-7h3g-55p8 nanoid) — separate from RLS.

## F. Integrated staging candidate

**`NO_CANDIDATE`**

Reasons (fail-closed):

1. Master SHA `5b9556c9` has no `staging-sha-proof` artifact.
2. Staging API fingerprint `161b58a3` ≠ master (last OCI deploy: PR #557, 2026-08-02).
3. No three-portal Vercel Preview proof at master SHA (`deploy-staging` run `30897217202` waiting on environment approval 107h+).
4. API code at `161b58a3` incompatible with staging DB at `0095`/RLS remediation tip.

## G. Remaining blockers (taxonomy)

| ID  | Taxonomy                      | Blocker                                                                              |
| --- | ----------------------------- | ------------------------------------------------------------------------------------ |
| B1  | **ENVIRONMENT_APPROVAL**      | `deploy-staging` run `30897217202` stuck `waiting` on `staging` environment          |
| B2  | **EXTERNAL_SERVICE**          | Staging API not redeployed since 2026-08-02; OCI SSH deploy required                 |
| B3  | **RATE_LIMIT**                | Vercel canceled vendor/admin production builds for `5b9556c9`                        |
| B4  | **BLOCKED_DATABASE** (prod)   | Production 25 migrations behind repo — not a staging gate but blocks prod parity     |
| B5  | **CI_FAILURE** (intermittent) | Nightly `deps-audit` nanoid advisory GHSA-2v37-7h3g-55p8                             |
| B6  | **UNKNOWN**                   | `PAYMENTS_ENABLED` / `PAYOUTS_ENABLED` runtime env on OCI — not readable without SSH |

## H. Production catch-up sequence (plan only — do not execute)

### Prerequisites

1. Full Supabase backup (`pg_dump`) with recorded `migration_tip=0071`.
2. Maintenance window + rollback decision recorded.
3. Confirm `PAYOUTS_ENABLED=false`, `PAYMENTS_ALLOW_PRODUCTION=false` on OCI.
4. CI green on target SHA including RLS + migration replay.

### Wave 0 — API/frontend alignment (no DB change)

1. Deploy API image at target SHA to production OCI.
2. Promote customer/vendor/admin Vercel production to same SHA (retry after rate-limit window).
3. Verify `/fingerprint` + `/{locale}/health` buildId match.

### Wave 1 — additive migrations 0072–0079 (dark-launch schema)

1. `supabase db push --include-all` on production (0072–0079).
2. Verify `feature_flags` rows for `clips`, `waha_vendor_intake` exist and remain **disabled**.
3. API smoke: gated routes return 404 when flags off.

### Wave 2 — commerce/location 0080–0090

1. Apply 0080–0090.
2. API compatibility: cart/reservation/location endpoints.
3. No payout activation.

### Wave 3 — governance 0091–0095

1. Apply 0091–0095 (admin roles, service categories, licence enforcement, analytics, RFQ).
2. Frontend smoke on RFQ/cart-merge flows.

### Wave 4 — RLS remediation

1. Apply `20260802153539_rls_policy_contract_remediation`.
2. Run `scripts/ci/check-staging-schema.sh` equivalent against production pooler.
3. Re-run full RLS matrix against production-like snapshot (never against live prod write path in CI).

### GO/NO-GO checkpoints

- After each wave: migration ledger count, advisors clean, API health, zero unexpected flag enables.
- Rollback: restore backup + pin previous API image; forward-fix preferred for additive-only migrations.

### Explicit non-actions

- Do **not** enable Clips, WAHA intake, wholesale expansion, live payments, or payouts merely because migrations exist.

## I. Verification performed this session

| Check                                           | Result                                |
| ----------------------------------------------- | ------------------------------------- |
| `bash scripts/ci/test-staging-guards.sh`        | 21 passed, 2 skipped (no local psql)  |
| Supabase `list_migrations` staging + production | Recorded above                        |
| Live `/fingerprint` staging + production        | Recorded above                        |
| Live customer `/en/health`                      | `buildId=5b9556c9`                    |
| Vercel deployment metadata                      | Customer/vendor/admin states recorded |
| `gh run list` master CI                         | `31279029410` in progress             |

## J. Verdict

**`BLOCKED_EXTERNAL`**

Repository and staging **database** are at git tip with safe flags, and RLS CI gates are correctly blocking. Integrated staging proof is impossible until staging API OCI redeploy + `deploy-staging` workflow completes (environment approval + Preview SHA proof at current master).
