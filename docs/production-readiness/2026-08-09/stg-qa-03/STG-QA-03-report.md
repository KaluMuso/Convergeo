# STG-QA-03 — Synthetic Marketplace + Deployed E2E + Recovery Proof

**Date:** 2026-08-09  
**Master SHA:** `c13d6692a66c4664efe9de31ba88d7e7b9066fe6`  
**Staging Supabase:** `iyasmrmbcrvlfxpzescb` (vergeo-sandbox, eu-west-1)  
**Production (untouched):** `dpadrlxukcjbewpqympu`

---

## Entry gate

| Surface                                | SHA         | Matches master?             |
| -------------------------------------- | ----------- | --------------------------- |
| **master**                             | `c13d6692…` | —                           |
| **api** (`api.staging.vergeo5.com`)    | `161b58a3…` | **NO** (237 commits behind) |
| **customer** (Vercel `staging` branch) | `c13d6692…` | YES                         |
| **vendor** (Vercel `staging` branch)   | `c13d6692…` | YES                         |
| **admin** (Vercel `staging` branch)    | `c13d6692…` | YES                         |

**Verdict:** `BLOCKED_DEPLOYMENT_IDENTITY`

`deploy-staging.yml` run [31315246673](https://github.com/KaluMuso/Convergeo/actions/runs/31315246673) has been **pending** since the PR #609 merge to `staging` (~2h). API OCI redeploy to `c13d6692` did not complete. Certification against deployed journeys was **not run** per entry conditions.

Canonical DNS (`staging.vergeo5.com`, `vendor.staging.vergeo5.com`, `admin.staging.vergeo5.com`) does not resolve; Vercel branch aliases are used instead.

---

## A. Live pre-seed inventory

See [`pre-seed-inventory.json`](./pre-seed-inventory.json).

| Entity                 | Count |
| ---------------------- | ----: |
| vendors                |     3 |
| vendor_listings        |     1 |
| listing_location_stock |     0 |
| vendor_locations       |     0 |
| carts                  |     5 |
| checkout_groups        |     0 |
| orders                 |     0 |
| payments               |     0 |
| business_buyers        |     0 |
| profiles (`stg-rv-*`)  |     6 |

All three vendors are synthetic (`stg-rv-20260719-vend-*`). Single listing on approved vendor at K125.00 (`12500` ngwee). API comparison probe returns `listing_count: 1`, `pickup_available: false`, `delivery_available: false`.

---

## B. Synthetic seed contract

See [`synthetic-seed-contract.json`](./synthetic-seed-contract.json).

**Tooling:** `scripts/seed_staging.py` (`stg-rv-20260719` prefix)

**Present:** 1 customer, 3 vendor personas (+ 2 admin), 1 product/listing, KYC records, idempotent guards.

**Missing vs STG-QA-03 contract:**

- Second customer (`cust-02`) and business buyer
- Second approved vendor + multi-seller Product A
- Products B (single-seller), C (OOS), D (wholesale-only / B2B)
- `vendor_locations` + `listing_location_stock`
- Cart/checkout/order state fixtures (9 order states)
- Cleanup script (manual checklist only)

---

## C. Post-seed inventory

No seed mutation this run (identity gate). Counts unchanged — see [`post-seed-inventory.json`](./post-seed-inventory.json).

---

## D. Staging-only safety proof

| Check                                         | Status                            |
| --------------------------------------------- | --------------------------------- |
| Rejects production ref `dpadrlxukcjbewpqympu` | **PASS**                          |
| Rejects `api.vergeo5.com` host                | **PASS**                          |
| Requires `--env staging`                      | **PASS**                          |
| `test_seed_staging.py`                        | **13/13 PASS**                    |
| `scripts/ci/test-staging-guards.sh`           | **21 pass**                       |
| Staging project confirmed via MCP             | **PASS** (`iyasmrmbcrvlfxpzescb`) |
| Production project untouched                  | **PASS**                          |

---

## E. RLS isolation

**Status:** `BLOCKED_DATABASE` (identity gate — live cross-persona tests not executed)

**Verified read-only:** RLS enabled on `carts`, `orders`, `vendor_listings`, `vendors`, `checkout_groups`.

**Not run:** Customer A/B cart/order isolation, vendor A/B mutation blocks, enquiry/RFQ/report flags with non-superuser JWTs against live staging.

Local matrix (`services/api/tests/rls/test_matrix.py` + `seed_matrix_fixtures`) covers these tables but uses `@rls-matrix.test` personas, not `stg-rv-*` auth users.

---

## F. Customer E2E journeys

**Status:** `NOT_RUN` — `BLOCKED_DEPLOYMENT_IDENTITY`

Mandatory journey (HOME → SEARCH → … → CHECKOUT safe-stop) not executed. Vercel Preview URLs require deployment protection bypass; customer staging branch is at master SHA but calls stale API at `161b58a3`.

---

## G. Payment-state UX

**Status:** `BLOCKED_EXTERNAL`

0 orders / 0 payments on staging. Lenco sandbox not exercised. No synthetic payment-state browser proofs. Stale API lacks recent PAY-01 / CUX-01 invariant behaviour.

---

## H. Discovery privacy/integrity

**Status:** `NOT_RUN` — `BLOCKED_DEPLOYMENT_IDENTITY`

Popular-search distinct-contributor threshold, trending session dedupe, email/phone/personal-query exclusion, and positive trending case not probed on deployed surfaces.

---

## I. Mobile/a11y

**Status:** `NOT_RUN` — `BLOCKED_DEPLOYMENT_IDENTITY`

Viewports 360×800 … 1440×900, axe smoke, modal focus trap — not run.

---

## J. Deployed performance

**Status:** `NOT_RUN` — `BLOCKED_DEPLOYMENT_IDENTITY`

LCP/CLS/INP/TTFB on home/search/category/PDP/cart/checkout not collected.

---

## K. Restore drill

**Status:** `BLOCKED_RECOVERY`

`backup_drill.sh --dry-run` → plan only (`verdict=SKIP`). No backup snapshot created, no controlled mutation marker, no restoration into safe non-production target verified this run. `RESTORE_DRILL_PROVEN` not claimed.

---

## L. Money-provider external blockers

| Blocker                  | Detail                                                      |
| ------------------------ | ----------------------------------------------------------- |
| Lenco sandbox            | Not exercised; `payment-sandbox` = `BLOCKED_EXTERNAL`       |
| Stale API                | Payment/order invariant endpoints 237 commits behind master |
| Zero transactional state | No orders to drive unpaid/success/failed/expired/COD UX     |

---

## M. Certificate evidence directory

```
docs/production-readiness/2026-08-09/stg-qa-03/
  deployment-identity-proof.json
  pre-seed-inventory.json
  post-seed-inventory.json
  synthetic-seed-contract.json
  release-certificate.json
  release-certificate.md
  STG-QA-03-report.md

scripts/qa/evidence/c13d6692a66c4664efe9de31ba88d7e7b9066fe6/staging/stg-qa-03-20260809/
  gate-*.json
  release-certificate.json
```

QA-02 collector verdict: `BASELINE_FAILING` (4 PASS / 2 FAIL / 1 BLOCKED_EXTERNAL / 20 NOT_RUN / 2 UNKNOWN).

---

## Unblock checklist (founder/ops)

1. **Approve** GitHub Environment `staging` for [deploy-staging run 31315246673](https://github.com/KaluMuso/Convergeo/actions/runs/31315246673) — or dispatch fresh workflow with `api_image_tag=c13d6692a66c4664efe9de31ba88d7e7b9066fe6`.
2. Confirm `GET https://api.staging.vergeo5.com/fingerprint` → `git_sha=c13d6692…`.
3. Extend `seed_staging.py` per STG-QA-03 contract (multi-seller, locations, order states).
4. Re-run STG-QA-03 certification.

---

## FINAL VERDICT

# `STAGING_QA_FAILED`

Primary causes: `BLOCKED_DEPLOYMENT_IDENTITY` (API stale), incomplete synthetic marketplace contract, `BLOCKED_RECOVERY`, `BLOCKED_EXTERNAL` (payments).
