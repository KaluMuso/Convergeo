# Batch 1A.3 — Staging API Candidate Evidence

**Date:** 2026-08-06  
**Session:** Batch 1A.3 official staging pipeline reconciliation + API deployment  
**Candidate SHA:** `cf76881746e3e37f491c048ff96a9b747de8e75b` (`master` frozen ✓)  
**Staging Supabase:** `iyasmrmbcrvlfxpzescb` (`vergeo-sandbox`, eu-west-1)  
**Production (untouched):** `dpadrlxukcjbewpqympu` · `api.vergeo5.com`

---

## 1. Candidate SHA

| Check                  | Result                                     |
| ---------------------- | ------------------------------------------ |
| `git rev-parse master` | `cf76881746e3e37f491c048ff96a9b747de8e75b` |
| Frozen candidate match | **PASS** — no `CANDIDATE_MOVED`            |

---

## 2. Official Staging Workflow Run

| Field               | Value                                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------- |
| Workflow            | `.github/workflows/deploy-staging.yml` (`Deploy staging`, id `308375370`)                                |
| Trigger attempted   | `workflow_dispatch` on ref `cf76881746e3e37f491c048ff96a9b747de8e75b`                                    |
| Inputs              | `skip_migrate=false`, `skip_vercel=true`, `seed_synthetic=false`, no `api_image_tag`                     |
| Result              | **NOT EXECUTED**                                                                                         |
| Error               | `HTTP 403: Resource not accessible by integration`                                                       |
| Staging environment | `required_reviewers` → `KaluMuso`; `can_admins_bypass=true`                                              |
| Stuck prior run     | `30897217202` — `waiting` on **Environment separation** since 2026-08-04 (SHA `b084b0d…`, not candidate) |

**STEP 1 pipeline safety review (static):** All required controls present in workflow YAML — staging environment, staging identifier guards, production ref/host hard-fails, `supabase link` + `db push --include-all`, `check-staging-schema.sh`, SHA-tagged GHCR build (refuses `latest`), OCI staging SSH deploy only, smoke fingerprint job. No redesign performed.

---

## 3. Migration Reconciliation Result

| Layer                                                    | Result                                         |
| -------------------------------------------------------- | ---------------------------------------------- |
| Official `supabase db push --include-all` (workflow job) | **NOT RUN** — workflow blocked                 |
| Independent MCP / SQL ledger audit                       | **ALIGNED** (see below)                        |
| Classification                                           | **RECONCILIATION NOT PROVEN VIA OFFICIAL CLI** |

### Remote ledger (`supabase_migrations.schema_migrations`)

- **96 migrations** applied; tip `20260802153539` / `rls_policy_contract_remediation`
- **0080–0095 band complete** — all 16 numeric migrations present with expected names
- **No duplicate versions** (`GROUP BY version HAVING count(*) > 1` → empty)
- **No gaps** in 0080–0095 sequence
- **No unexpected remote-only** migrations beyond Git tip

Required migrations verified present:

`0080_vendor_location_details` · `0081_listing_location_stock` · `0082_enquiry_threads` · `0083_vendor_follows` · `0084_vendor_licences` · `0085_product_classes` · `0086_cart_line_price_guard` · `0087_product_class_enum` · `0088_user_saves` · `0089_vendor_locations_geo_index` · `0090_stock_reservation_location` · `0091_admin_moderator_roles` · `0092_service_categories` · `0093_license_expiry_enforcement` · `0094_vendor_storefront_collections_listing_analytics` · `0095_rfq_threads` · `20260802153539_rls_policy_contract_remediation`

**Note:** Batch 1A.2 applied these via MCP SQL + manual ledger INSERT. Official CLI reconciliation remains the outstanding proof item.

---

## 4. Schema/RLS Gate

| Layer                                                                 | Result      |
| --------------------------------------------------------------------- | ----------- |
| Official workflow `check-staging-schema.sh` + `check-db-reachable.sh` | **NOT RUN** |
| Independent SQL (same logic as `scripts/ci/check-staging-schema.sql`) | **PASS**    |

Independent checks on staging DB:

- Public base tables without RLS → **0 rows** (no `FAIL table without RLS`)
- Exposed public views without `security_invoker` → **0 rows** (no `FAIL exposed view`)

**Classification:** Schema/RLS posture looks healthy, but **official pipeline gate not executed** — cannot accept as workflow-green.

---

## 5. API Deployment Result

| Field                                            | Value                                             |
| ------------------------------------------------ | ------------------------------------------------- |
| GHCR image `ghcr.io/.../convergeo-api:cf768817…` | **NOT BUILT**                                     |
| OCI staging deploy                               | **NOT EXECUTED**                                  |
| Deployed image (live)                            | `ghcr.io/.../convergeo-api:161b58a3…` (pre-batch) |

---

## 6. Fingerprint (live staging — pre-deploy state)

Probed `https://api.staging.vergeo5.com` at session time:

| Endpoint                | HTTP | Key fields                                                                                                     |
| ----------------------- | ---- | -------------------------------------------------------------------------------------------------------------- |
| `/healthz`              | 200  | `status=ok`                                                                                                    |
| `/readyz`               | 200  | `search_embedding=degraded`                                                                                    |
| `/readyz?checks=search` | 200  | `search_rpc=ok`, `search_embedding=degraded`                                                                   |
| `/fingerprint`          | 200  | `env=staging`, `git_sha=161b58a3e1973b79abd4fc8064611c50fa0268c8`, `supabase_project_ref=iyasmrmbcrvlfxpzescb` |

| Requirement                                    | Result                      |
| ---------------------------------------------- | --------------------------- |
| `git_sha == cf768817…`                         | **FAIL** — live `161b58a3…` |
| `supabase_project_ref == iyasmrmbcrvlfxpzescb` | **PASS**                    |

Deployed SHA `161b58a3` is an ancestor of candidate `cf768817` (0 commits between).

---

## 7. Router Registration Matrix (live staging API @ `161b58a3`)

Interpretation: 401/403/405 = router present; 404 = absent.

| Route                                              | HTTP         | Router @ deployed SHA                          |
| -------------------------------------------------- | ------------ | ---------------------------------------------- |
| `GET /enquiries`                                   | 404          | **ABSENT** (file not in `161b58a3`)            |
| `GET /rfq`                                         | 404          | **ABSENT**                                     |
| `GET /categories`                                  | 404          | **ABSENT** (`categories.py` not in `161b58a3`) |
| `GET /catalog/listings`                            | 200          | PRESENT                                        |
| `GET /search?q=test`                               | 200          | PRESENT                                        |
| `GET /cart`                                        | 200          | PRESENT                                        |
| `GET /search/suggest?q=te`                         | 200          | PRESENT                                        |
| `GET /products/stg-rv-20260719-product`            | 200          | PRESENT                                        |
| `GET /products/stg-rv-20260719-product/comparison` | 500          | PRESENT (error, not 404)                       |
| `GET /follows`                                     | 404          | **ABSENT**                                     |
| `GET /me/follows`                                  | (not probed) | **ABSENT** at SHA                              |
| `GET /clips`                                       | 405          | PRESENT                                        |
| `POST /internal/stock-sweeper/tick`                | 405          | PRESENT                                        |

**Post-candidate expectation:** `enquiries`, `rfq`, `categories`, `follows` routers exist in `cf768817` tree — deployment required to prove registration.

---

## 8. Core Retail Regression (live @ `161b58a3`)

| Capability          | HTTP | Notes                                  |
| ------------------- | ---- | -------------------------------------- |
| Catalogue listings  | 200  | Synthetic listing returned             |
| Categories (public) | 404  | Router not deployed                    |
| Product lookup      | 200  | `stg-rv-20260719-product`              |
| Listing lookup      | 200  | via `/catalog/listings`                |
| Search              | 200  | 2 results for `test`                   |
| Search suggestions  | 200  | `/search/suggest` (empty suggestions)  |
| Comparison          | 500  | Router present; internal error on slug |
| Geo/nearby          | 404  | No `/geo/nearby` in deployed openapi   |
| Cart read           | 200  | Empty cart                             |
| Health              | 200  | `/healthz`                             |
| Readiness           | 200  | `/readyz`, search RPC ok               |

No payment or order creation initiated.

---

## 9. Post-0079 Capability Regression (live @ `161b58a3`)

| Capability                    | DB (staging) | API route (deployed)                    | Notes                                 |
| ----------------------------- | ------------ | --------------------------------------- | ------------------------------------- |
| Vendor locations (0080)       | PRESENT      | Partial (embedded in catalog/directory) | No dedicated locations router probed  |
| Listing-location stock (0081) | PRESENT      | UNKNOWN                                 | Server path only                      |
| Enquiries (0082)              | PRESENT      | **ABSENT** (404)                        | Expected until API deploy             |
| Vendor follows (0083)         | PRESENT      | **ABSENT** (404)                        | `/me/follows` in candidate code       |
| Vendor licences (0084)        | PRESENT      | **ABSENT** (404 at `/vendor/licences`)  | Admin licences in candidate           |
| Product classes (0085–0087)   | PRESENT      | UNKNOWN                                 | Schema-only until listing writes      |
| User saves (0088)             | PRESENT      | **NOT_DEPLOYED**                        | Table only; no public router in repo  |
| Moderator roles (0091)        | PRESENT      | UNKNOWN                                 | Admin-only; no staging creds          |
| Service categories (0092)     | PRESENT      | **ABSENT**                              | Taxonomy table; no public route found |
| Storefront collections (0094) | PRESENT      | UNKNOWN                                 | `/vendor/collections` in candidate    |
| Listing analytics (0094)      | PRESENT      | UNKNOWN                                 | Vendor analytics router               |
| RFQ (0095)                    | PRESENT      | **ABSENT** (404)                        | Expected until API deploy             |

---

## 10. Cart Security (CAN-ORD-002)

| Check                                   | Result                                   |
| --------------------------------------- | ---------------------------------------- |
| `anon` INSERT on `cart_items`           | **DENIED** — grant absent                |
| `anon` UPDATE on `cart_items`           | **DENIED** — grant absent                |
| `authenticated` INSERT                  | **DENIED** — grant absent                |
| `authenticated` UPDATE                  | **DENIED** — grant absent                |
| `anon`/`authenticated` SELECT + DELETE  | Present (expected)                       |
| Full persona RLS pytest against staging | **NOT RUN** — no `SUPABASE_DB_URL` in VM |

**Classification:** **PARTIAL_RUNTIME_VERIFICATION** — grant revocation confirmed via `information_schema.role_table_grants`; no live authenticated INSERT attempt.

---

## 11. Feature Flags

All required flags **disabled** on staging DB (`feature_flags.flag`):

| Flag                 | Enabled |
| -------------------- | ------- |
| `public_launch`      | false   |
| `clips`              | false   |
| `waha_vendor_intake` | false   |
| `paid_tiers`         | false   |
| `wallet`             | false   |
| `zamtel_collections` | false   |
| `abandoned_cart`     | false   |

Schema/API deploy did not run; flags unchanged from Batch 1A.2 posture.

---

## 12. Financial Safety

| Table                 | Count | Delta this session |
| --------------------- | ----- | ------------------ |
| `orders`              | 0     | 0                  |
| `payments`            | 0     | 0                  |
| `ledger_transactions` | 0     | 0                  |

No payment sweeper triggered. No Lenco drills. No escrow releases.

---

## 13. n8n Observation

Workflows **ACTIVE**; recent executions **success** (observed 2026-08-06 ~21:20 UTC):

| Workflow                                          | Status | Recent executions         |
| ------------------------------------------------- | ------ | ------------------------- |
| Reservation sweeper (`F25zEWiPoIveARys`)          | ACTIVE | **HEALTHY** (5/5 success) |
| Notification dispatch (`sevKtX1AmimQCWsG`)        | ACTIVE | **HEALTHY** (5/5 success) |
| Embeddings cron (`oqjfSdMXClfsf3qd`)              | ACTIVE | **HEALTHY** (5/5 success) |
| Payment reconciliation crons (`C1MpTNjrfLACMG3f`) | ACTIVE | **HEALTHY** (5/5 success) |

No schema/API regression signals observed in execution status after Batch 1A.2 schema apply. Reconciliation workflow description still references `api.vergeo5.com` in n8n metadata — **not modified this session**.

---

## 14. Enquiries Triangle

| Layer                     | State                                                              |
| ------------------------- | ------------------------------------------------------------------ |
| Database                  | **PRESENT** (`enquiry_threads`, `enquiry_messages`)                |
| API                       | **ABSENT** on deployed SHA (`GET /enquiries` → 404)                |
| Customer CTA (production) | **NOT_TESTED** (`vergeo5.com` redirect only)                       |
| Customer CTA (staging)    | **HIDDEN** (fail-closed: 404 → hide per `enquiries-capability.ts`) |

---

## 15. RFQ Triangle

| Layer                | State                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| Database             | **PRESENT** (`rfq_threads`, `rfq_messages`)                                                    |
| API route            | **ABSENT** on deployed SHA (`GET /rfq` → 404)                                                  |
| Vendor UI route      | **NOT_DEPLOYED** (`apps/vendor/.../rfq/page.tsx` exists in Git; vendor staging URL not probed) |
| Customer entry route | **NOT_TESTED**                                                                                 |

B2B not activated — flags remain off, no RFQ API on live staging.

---

## 16. Evidence Produced

- This file: `docs/production-readiness/2026-08-06/staging-api-candidate-evidence.md`
- Branch: `cursor/batch1a3-staging-api-evidence-afb5`
- Shared programme ledgers **not edited** (parallel-session safe)

---

## 17. STAGING API GATE

### **BLOCKED_EXTERNAL**

The authorized official staging pipeline could not be invoked:

1. `workflow_dispatch` rejected (`403 Resource not accessible by integration`).
2. GitHub Environment `staging` requires reviewer approval (`KaluMuso`); prior run `30897217202` stuck in `waiting`.
3. No `SUPABASE_ACCESS_TOKEN`, OCI SSH keys, or staging DB URL in agent VM — cannot substitute manual deploy/CLI/MCP apply per programme rules.

Consequences:

- Official `supabase db push` reconciliation **not proven**.
- Official schema/RLS CI gate **not executed** (independent SQL passed).
- Candidate API image **not built or deployed**.
- Live fingerprint **wrong SHA** (`161b58a3` ≠ `cf768817`).
- Enquiries/RFQ routers **still absent** on live staging.

Production untouched.

---

## 18. EXACT Recommended Next Action

**Founder action (blocking):**

1. Approve the waiting GitHub Actions run **or** dispatch **Deploy staging** manually from GitHub UI on commit `cf76881746e3e37f491c048ff96a9b747de8e75b` with:
   - `skip_migrate = false`
   - `skip_vercel = true`
   - `seed_synthetic = false`
   - leave `api_image_tag` empty (use workflow `github.sha`)
2. Confirm the **Supabase migrations + checks** job reports clean `db push` (no re-apply of 0080–0095, no `migration repair` prompt).
3. After deploy, re-run Batch 1A.3 verification probes (fingerprint SHA, `/enquiries` → 401/403, `/rfq` → 401/403, `/categories` → 200).

**Optional follow-up:** Grant the Cursor Cloud agent `workflow_dispatch` permission or pre-approve staging environment for automation.

Do not touch production Supabase or `api.vergeo5.com`.
