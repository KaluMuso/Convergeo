# Production Migration Catch-Up Plan — Batch 1A

**Date:** 2026-08-06  
**Repository SHA:** `e7555b8d80e4cf6ca1a5f240a913ef8dc9381306` (`cursor/batch1a-migration-catchup-plan-9b44`)  
**Mode:** READ-ONLY analysis — **no migrations applied, no deploys executed**

---

## 1. Verified baseline (reconfirmed 2026-08-06)

| Layer              | Tip / identity                                                                | Evidence                                                |
| ------------------ | ----------------------------------------------------------------------------- | ------------------------------------------------------- |
| **Production DB**  | `0071_vendor_listing_compare_at`                                              | Supabase MCP `list_migrations` (`dpadrlxukcjbewpqympu`) |
| **Staging DB**     | `0079_clip_cost_guard`                                                        | Supabase MCP (`iyasmrmbcrvlfxpzescb`)                   |
| **Git migrations** | `0095_rfq_threads.sql` + `20260802153539_rls_policy_contract_remediation.sql` | `supabase/migrations/` (96 `00*.sql` + 1 timestamp)     |
| **Production API** | `git_sha=e4a7bb79`                                                            | `GET https://api.vergeo5.com/fingerprint`               |
| **Customer FE**    | `buildId=fcf2b191` (matches `master`)                                         | `GET https://vergeo5.com/en/health`                     |
| **RLS CI**         | TRUSTWORTHY                                                                   | Batch 0.5; `vergeo_rls_tester` + blocking step          |
| **Triple 0093**    | Remediated (`0093`/`0094`/`0095`)                                             | PR #583                                                 |

**Production data snapshot (read-only):**

| Metric              | Count                     |
| ------------------- | ------------------------- |
| Vendors             | 3                         |
| Vendor locations    | 0                         |
| Active listings     | 134 (all `condition=new`) |
| Cart items          | 0                         |
| Orders              | 0                         |
| Ledger transactions | 0                         |

---

## 2. Migration inventory (0072 → 0095 + timestamp)

| #    | File                                                       | Purpose                                                 | Classification                                       | Compat (old API)     | Compat (master API) | Flags                     | CAN-*                    |
| ---- | ---------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------- | -------------------- | ------------------- | ------------------------- | ------------------------ |
| 0072 | `0072_waha_intake_flag.sql`                                | Seed `waha_vendor_intake` + allowlist config (OFF)      | DATA_BACKFILL, FEATURE_SPECIFIC                      | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | `waha_vendor_intake`      | —                        |
| 0073 | `0073_waha_intake_model.sql`                               | 7 intake tables + FORCE RLS                             | ADDITIVE_SAFE, RLS_SECURITY_CHANGE, FEATURE_SPECIFIC | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | (0072)                    | —                        |
| 0074 | `0074_intake_media_bucket.sql`                             | Private storage bucket (conditional)                    | ADDITIVE_WITH_DEPENDENCY, RLS_SECURITY_CHANGE        | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | —                        |
| 0075 | `0075_intake_handoff.sql`                                  | Session→listing handoff + deep links                    | ADDITIVE_SAFE, RLS_SECURITY_CHANGE                   | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | —                        |
| 0076 | `0076_video_clips.sql`                                     | 6 clip tables + guards + public feed RLS                | ADDITIVE_SAFE, RLS_SECURITY_CHANGE, FEATURE_SPECIFIC | BACKWARD_COMPATIBLE  | DUAL_COMPATIBLE*    | —                         | —                        |
| 0077 | `0077_clip_feature_flags.sql`                              | Seed `clips`, `clips_comments` (OFF)                    | DATA_BACKFILL, FEATURE_SPECIFIC                      | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | `clips`, `clips_comments` | —                        |
| 0078 | `0078_clip_weekly_caps.sql`                                | Weekly upload caps config                               | DATA_BACKFILL, FEATURE_SPECIFIC                      | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | `clip_weekly_caps`        | —                        |
| 0079 | `0079_clip_cost_guard.sql`                                 | Monthly clip spend + kill switch RPCs                   | ADDITIVE_SAFE, RLS_SECURITY_CHANGE                   | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | `clip_monthly_cap_usd`    | —                        |
| 0080 | `0080_vendor_location_details.sql`                         | Branch label/address/phone/primary/status + RLS tighten | ADDITIVE_SAFE, RLS_SECURITY_CHANGE, DATA_BACKFILL    | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | CAN-CAT-004              |
| 0081 | `0081_listing_location_stock.sql`                          | Per-branch stock table + backfill from primary          | ADDITIVE_WITH_DEPENDENCY, DATA_BACKFILL              | DUAL_COMPATIBLE      | DUAL_COMPATIBLE     | —                         | CAN-CAT-004, CAN-CAT-005 |
| 0082 | `0082_enquiry_threads.sql`                                 | Listing-anchored enquiry threads                        | FEATURE_SPECIFIC, ADDITIVE_SAFE, RLS_SECURITY_CHANGE | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-SOC-001              |
| 0083 | `0083_vendor_follows.sql`                                  | One-way vendor follows                                  | FEATURE_SPECIFIC, ADDITIVE_SAFE                      | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-SOC-001              |
| 0084 | `0084_vendor_licences.sql`                                 | Regulator licence records + validity fn                 | FEATURE_SPECIFIC, ADDITIVE_SAFE, RLS_SECURITY_CHANGE | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-ID-003               |
| 0085 | `0085_product_classes.sql`                                 | Sale units, MTO, used condition + line total fn         | ADDITIVE_SAFE, FEATURE_SPECIFIC                      | BACKWARD_COMPATIBLE  | DUAL_COMPATIBLE     | —                         | CAN-ORD-003, CAN-FIN-006 |
| 0086 | `0086_cart_line_price_guard.sql`                           | Revoke client INSERT/UPDATE on `cart_items`             | RLS_SECURITY_CHANGE                                  | **DUAL_COMPATIBLE**† | DUAL_COMPATIBLE     | —                         | CAN-ORD-002              |
| 0087 | `0087_product_class_enum.sql`                              | Classes A–E on listings                                 | ADDITIVE_WITH_DEPENDENCY                             | BACKWARD_COMPATIBLE  | DUAL_COMPATIBLE     | —                         | CAN-CAT-001              |
| 0088 | `0088_user_saves.sql`                                      | Polymorphic product/event saves                         | FEATURE_SPECIFIC, ADDITIVE_SAFE                      | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-SOC-001              |
| 0089 | `0089_vendor_locations_geo_index.sql`                      | Lat/lng index for nearby                                | ADDITIVE_SAFE                                        | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | CAN-DISC-002             |
| 0090 | `0090_stock_reservation_location.sql`                      | `pickup_location_id` on cart/reservations               | ADDITIVE_SAFE                                        | BACKWARD_COMPATIBLE  | DUAL_COMPATIBLE     | —                         | CAN-CAT-005              |
| 0091 | `0091_admin_moderator_roles.sql`                           | `superadmin`/`moderator` in `user_roles` CHECK          | ADDITIVE_SAFE                                        | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | CAN-ADM-002              |
| 0092 | `0092_service_categories.sql`                              | Service taxonomy reference table                        | ADDITIVE_SAFE, RLS_SECURITY_CHANGE                   | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-CAT-001              |
| 0093 | `0093_license_expiry_enforcement.sql`                      | Licence expiry enum + `suspended_compliance`            | ADDITIVE_WITH_DEPENDENCY, DATA_BACKFILL              | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-ID-003               |
| 0094 | `0094_vendor_storefront_collections_listing_analytics.sql` | Storefront collections + listing analytics              | FEATURE_SPECIFIC, ADDITIVE_SAFE, RLS_SECURITY_CHANGE | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-VND-002              |
| 0095 | `0095_rfq_threads.sql`                                     | B2B RFQ threads + `cart_items.rfq_thread_id`            | FEATURE_SPECIFIC, ADDITIVE_SAFE, RLS_SECURITY_CHANGE | BACKWARD_COMPATIBLE  | **DB_FIRST**        | —                         | CAN-CAT-003              |
| TS   | `20260802153539_rls_policy_contract_remediation.sql`       | Narrow review-reply guard bypass (security)             | RLS_SECURITY_CHANGE                                  | BACKWARD_COMPATIBLE  | BACKWARD_COMPATIBLE | —                         | CAN-OPS-001              |

\* Master API `clips.py` queries `video_clips` without flag check on feed routes — safe only while `clips` flag OFF and route unused.  
† Deployed API `e4a7bb79` already writes cart via `service_role` (`cart/store.py`); 0086 does not break it. Breaks only direct PostgREST cart writes.

**Financial migrations (0072–0095):** No changes to `ledger_*`, `payments`, `escrow` tables or money state machines. Ngwee references are additive columns/functions only. **Safe while payments disabled.**

---

## 3. Deployment compatibility matrix

| DB state         | API state             | Customer FE             | Vendor/Admin         | Expected compatibility            | Evidence                                                                              |
| ---------------- | --------------------- | ----------------------- | -------------------- | --------------------------------- | ------------------------------------------------------------------------------------- |
| Prod **0071**    | Deployed **e4a7bb79** | **master** (`fcf2b191`) | Unknown / CF-blocked | **PARTIAL — social UI broken**    | `/enquiries` → **404** on prod API; Contact Vendor on PDP calls missing route         |
| Prod **0071**    | **master**            | master                  | Unknown              | **BROKEN** for new routes         | `enquiries.py`, `rfq.py` query tables absent; `clips` queries `video_clips` (missing) |
| Staging **0079** | Deployed **e4a7bb79** | master                  | Unknown              | **PARTIAL**                       | Clips/intake schema present; social/RFQ/licences absent                               |
| Staging **0079** | master                | master                  | Unknown              | **BROKEN** for 0082+ routes       | Same as prod + clips tables exist (clips API OK if flag on)                           |
| **0095+TS**      | **e4a7bb79**          | master                  | Unknown              | **PARTIAL**                       | Schema ahead; API missing enquiries/RFQ handlers                                      |
| **0095+TS**      | **master**            | master                  | Unknown              | **MATCHES** (target steady state) | Full schema + full API; flags still gate features                                     |

**Safe transition path:** DB catch-up **before** (or in the same maintenance window as) API deploy to `master`. Customer FE is already at `master` — **do not wait for FE deploy**; gate or accept broken social paths until API+DB aligned.

---

## 4. Code → migration dependency map

| Code feature                       | Required migration(s)      | Feature flag             | Prod exposure today                                                                                  |
| ---------------------------------- | -------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------- |
| WAHA vendor intake                 | 0072–0075 (+ 0074 storage) | `waha_vendor_intake` OFF | None (flag + no webhook traffic)                                                                     |
| Vergeo Clips feed/upload           | 0076–0079                  | `clips` OFF              | Customer `/clips` → `notFound()`; API `/clips/*` exists on e4a7bb79 but **no table** → 500 if called |
| Vendor branches / branch stock     | 0080, 0081, 0090           | —                        | Master code may reference columns; prod DB lacks them → **graceful if paths unused**                 |
| Contact vendor (enquiries)         | **0082**                   | —                        | **LIVE RISK:** PDP shows button; API **404**                                                         |
| Vendor follows                     | 0083                       | —                        | Low traffic; API route may 404                                                                       |
| Vendor licences                    | 0084, 0093                 | —                        | Vendor onboarding paths on master API only                                                           |
| Product classes A–E / MTO          | 0085, 0087                 | —                        | `product_class` absent on prod listings API; RFQ button hidden (class E)                             |
| Cart price tamper fix              | **0086**                   | —                        | Cart empty; API uses service_role already                                                            |
| User saves                         | 0088                       | —                        | Low exposure                                                                                         |
| Geo nearby index                   | 0089                       | —                        | Search works on 0071 schema                                                                          |
| RFQ quote flow                     | **0092**, **0095**         | —                        | Class E button rare; API **404** if clicked                                                          |
| Storefront collections / analytics | 0094                       | —                        | Vendor/admin only                                                                                    |
| Admin moderator roles              | 0091                       | —                        | Admin only                                                                                           |
| Review reply guard fix             | timestamp TS               | —                        | Security-only; no product surface                                                                    |

**Why customer FE at master + prod DB at 0071 does not crash retail browse:** Core catalog/checkout paths use pre-0072 schema; new columns are optional in API responses; broken paths are **opt-in UI actions** (contact vendor, RFQ, clips route).

---

## 5. RLS migration coverage (post-0071)

| Migration  | Policy / grant change            | RLS test                                       | Coverage    |
| ---------- | -------------------------------- | ---------------------------------------------- | ----------- |
| 0073–0075  | Intake tables FORCE RLS          | `test_intake_force_rls.py`, matrix entries     | **COVERED** |
| 0076, 0079 | Clips + spend tables             | `test_clips_rls.py`, matrix                    | **COVERED** |
| 0080       | `vendor_locations` public policy | matrix `vendor_locations`                      | **COVERED** |
| 0081       | `listing_location_stock`         | matrix                                         | **COVERED** |
| 0082       | `enquiry_*`                      | matrix                                         | **COVERED** |
| 0083       | `vendor_follows`                 | matrix                                         | **COVERED** |
| 0084       | `vendor_licences`                | matrix                                         | **COVERED** |
| 0086       | **GRANT revoke** on `cart_items` | matrix (row policies); **grants not asserted** | **PARTIAL** |
| 0088       | `user_saves`                     | matrix                                         | **COVERED** |
| 0094       | collections + analytics          | matrix                                         | **COVERED** |
| 0095       | `rfq_*`                          | matrix (added PR #582)                         | **COVERED** |
| TS         | Function replace only            | `test_review_reply_guard.py`                   | **COVERED** |

---

## 6. Financial migration safety

| Question                          | Answer                  |
| --------------------------------- | ----------------------- |
| Modifies existing financial rows? | **No** (0072–0095 band) |
| Backfills money data?             | **No**                  |
| Alters ledger invariants?         | **No**                  |
| Depends on money exercised?       | **No**                  |
| Safe with PAYMENTS disabled?      | **Yes**                 |

RFQ `quote_price_ngwee` is schema-only until quotes are sent; zero orders/carts on prod.

---

## 7. Production data compatibility (read-only)

| Table              | Constraint (from migration)         | Violating rows          | Risk    |
| ------------------ | ----------------------------------- | ----------------------- | ------- |
| `vendor_locations` | 0080 backfill primary               | **N/A** (0 rows)        | **LOW** |
| `vendor_listings`  | 0085 `used` requires `defect_notes` | **0** (all `new`)       | **LOW** |
| `vendor_listings`  | 0087 class D ⇒ `used`               | **0** used listings     | **LOW** |
| `cart_items`       | 0086 revoke client writes           | **0** rows              | **LOW** |
| `vendor_licences`  | 0093 backfill `license_body`        | Table absent until 0084 | **N/A** |

---

## 8. Migration replay verification

| Environment                            | Result                          | Notes                                                      |
| -------------------------------------- | ------------------------------- | ---------------------------------------------------------- |
| CI `migration-replay.sh`               | **Reliable for `00*.sql` only** | `.github/workflows/ci.yml` job `migrations`; PR #583 green |
| Timestamp migration `20260802153539_*` | **NOT in replay script**        | `find … -name '00*.sql'` excludes it — **gap**             |
| Local Docker replay                    | **BLOCKED_EXTERNAL**            | `docker: command not found` in Cloud Agent VM              |
| `supabase db reset` (full)             | **Expected OK**                 | RLS job runs full reset + `tests/rls`                      |

**Defect:** Fast replay does not apply timestamp migration — classify as **migration tooling gap** (see BLK-201).

---

## 9. Proposed migration waves

### Wave A — Isolated feature schema (0072–0079)

| Field                 | Value                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Preconditions**     | Prod backup/PITR confirmed; maintenance window optional (additive only)                                                  |
| **Migrations**        | `0072` … `0079`                                                                                                          |
| **Schema changes**    | Intake + clips tables; feature flag seeds (all OFF)                                                                      |
| **Features affected** | None at retail (flags OFF)                                                                                               |
| **Flags**             | `waha_vendor_intake`, `clips`, `clips_comments` remain **false**                                                         |
| **Verify**            | `SELECT flag, enabled FROM feature_flags WHERE flag IN ('clips','waha_vendor_intake');` — tables exist: `\d video_clips` |
| **RLS**               | `uv run pytest tests/rls/test_clips_rls.py tests/rls/test_intake_force_rls.py` (on staging after apply)                  |
| **API smoke**         | `/healthz`, `/readyz?checks=search`; **do not** enable clips flag                                                        |
| **Rollback**          | Drop new tables in reverse order (documented in migration headers); delete flag rows                                     |
| **GO**                | All migrations apply cleanly; RLS green; no error rate spike                                                             |
| **NO-GO**             | Any migration failure; storage bucket step fails on prod Supabase                                                        |

**Staging evidence:** Wave A **already applied** on staging (`0079` tip).

---

### Wave B — Vendor branches & stock (0080–0081, 0089–0090)

| Field                 | Value                                                                                |
| --------------------- | ------------------------------------------------------------------------------------ |
| **Preconditions**     | Wave A complete (prod)                                                               |
| **Migrations**        | `0080`, `0081`, `0089`, `0090`                                                       |
| **Schema changes**    | Branch columns; `listing_location_stock`; geo index; reservation location FKs        |
| **Features affected** | Checkout pickup selection (when locations exist); reservation sweeper location-aware |
| **Flags**             | —                                                                                    |
| **Verify**            | `SELECT COUNT(*) FROM listing_location_stock;` — backfill count vs tracked listings  |
| **RLS**               | matrix `vendor_locations`, `listing_location_stock`                                  |
| **Rollback**          | Drop 0090 columns; drop 0081 table; revert 0080 columns/policies                     |

**Prod risk:** **LOW** (0 locations today; backfill creates no rows).

---

### Wave C — Social commerce (0082, 0083, 0088)

| Field                 | Value                                                           |
| --------------------- | --------------------------------------------------------------- |
| **Preconditions**     | Wave B complete; **API deploy ≥ `1d2e3b37`** (enquiries router) |
| **Migrations**        | `0082`, `0083`, `0088`                                          |
| **Features affected** | Contact vendor, follows, saves                                  |
| **Flags**             | —                                                               |
| **Verify**            | `POST /enquiries` smoke (staging); RLS matrix                   |
| **Coordination**      | **DB_FIRST then API** — fixes prod Contact Vendor **404**       |

---

### Wave D — Compliance & product taxonomy (0084–0085, 0087, 0091–0093, 0092)

| Field                 | Value                                                                    |
| --------------------- | ------------------------------------------------------------------------ |
| **Preconditions**     | Wave C complete                                                          |
| **Migrations**        | `0084` → `0085` → `0087` → `0091` → `0092` → `0093` (order respects FKs) |
| **Features affected** | Licences, product classes, service taxonomy, admin roles                 |
| **Verify**            | Licence validity RPC; listing defaults `product_class='A'`               |

---

### Wave E — Cart security hardening (0086)

| Field             | Value                                                                       |
| ----------------- | --------------------------------------------------------------------------- |
| **Preconditions** | API confirmed using `service_role` for all cart writes (true on `e4a7bb79`) |
| **Migrations**    | `0086`                                                                      |
| **Coordination**  | **DUAL_COMPATIBLE** — may apply before or after API deploy                  |
| **Verify**        | Attempt PostgREST cart insert as authenticated → denied                     |

---

### Wave F — B2B RFQ + storefront analytics (0094–0095)

| Field             | Value                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| **Preconditions** | Wave D complete (`0087` class E); **API deploy ≥ `d9f10ba1`** (RFQ router) |
| **Migrations**    | `0094`, `0095`                                                             |
| **Coordination**  | **DB_FIRST then API**                                                      |

---

### Wave G — RLS security remediation (timestamp)

| Field             | Value                                                |
| ----------------- | ---------------------------------------------------- |
| **Preconditions** | `0061`/`0063` already on prod (yes, at 0071)         |
| **Migrations**    | `20260802153539_rls_policy_contract_remediation.sql` |
| **Coordination**  | Independent; **anytime** after Wave A                |
| **Verify**        | `tests/rls/test_review_reply_guard.py`               |

---

## 10. API deployment sequence

**Recommended order:**

1. **Wave A (DB)** on production — no API change required.
2. **Wave B (DB)** on production — no API change required for current traffic.
3. **Deploy API to `master`** (or minimum SHA **`d9f10ba1`** for RFQ, **`1d2e3b37`** for enquiries only) — **only after Waves C+F schema ready**, OR deploy in lockstep per wave.
4. **Waves C, D, E, F (DB)** per schedule above.
5. **Wave G (DB)** anytime after step 1.
6. **Final API** at `master` HEAD after DB at `0095+TS`.

**Do not** deploy `master` API to prod **0071** without accepting 404/500 on new routes.

**First API SHA per wave:**

| After DB wave | Minimum API SHA      | Capability unlocked                  |
| ------------- | -------------------- | ------------------------------------ |
| Wave A        | `e4a7bb79` (current) | Clips/intake schema only (flags OFF) |
| Wave C        | `1d2e3b37`+          | `/enquiries`                         |
| Wave F        | `d9f10ba1`+          | `/rfq`                               |
| Full          | `fcf2b191`+ (master) | All routers                          |

---

## 11. Frontend compatibility risks

| Path                            | Risk                                                                                    | Mitigation                                       |
| ------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| PDP **Contact Vendor**          | **HIGH** — FE calls `/enquiries`; prod API **404**                                      | Apply Wave C + API deploy; or gate UI until then |
| PDP **Request Quote** (class E) | **MEDIUM** — needs `/rfq` + 0095                                                        | Rare (no class E listings on prod); API 404      |
| `/clips` route                  | **LOW** — FE checks `clips` flag (OFF); prod flag row absent = fail-closed `notFound()` | Keep flag OFF                                    |
| Core browse/checkout            | **LOW**                                                                                 | Uses pre-0072 schema                             |

---

## 12. n8n schema dependencies

| Workflow               | Endpoint                       | Post-0071 schema needed?                       | Classification                         |
| ---------------------- | ------------------------------ | ---------------------------------------------- | -------------------------------------- |
| Reservation sweeper    | `/internal/stock-sweeper/tick` | **Optional** `0090` for location-aware release | **SAFE_ON_0071** (degrades gracefully) |
| Payment reconciliation | `/internal/reconciliation/*`   | No                                             | **SAFE_ON_0071**                       |
| Notification dispatch  | `/internal/notifications/*`    | No                                             | **SAFE_ON_0071**                       |
| Embeddings cron        | `/internal/embeddings/tick`    | No (`embedding_jobs` ≤0071)                    | **SAFE_ON_0071**                       |
| Analytics retention    | internal API                   | No                                             | **SAFE_ON_0071**                       |

No ACTIVE n8n workflow requires 0072+ tables on prod today.

---

## 13. Blockers (Batch 1A)

| ID          | Category               | Description                                                                 |
| ----------- | ---------------------- | --------------------------------------------------------------------------- |
| BLK-201     | CODE_DEFECT            | `migration-replay.sh` skips timestamp migration `20260802153539_*`          |
| BLK-202     | DEPLOYMENT_REQUIRED    | Customer FE master + prod API `e4a7bb79` + prod DB `0071` triangle mismatch |
| BLK-203     | CODE_DEFECT            | Clips public API lacks `clips_enabled()` gate before DB query               |
| BLK-001/002 | DATA_MIGRATION_BLOCKER | (from Batch 0.5) prod/staging behind Git                                    |

---

## 14. GO / NO-GO gates (production catch-up)

**GO for Wave A on production when:**

- [ ] Supabase backup/PITR status confirmed (EXT-004)
- [ ] Staging at 0079 healthy for 48h+ (already applied)
- [ ] Rollback runbook reviewed
- [ ] Feature flags confirmed OFF post-apply

**NO-GO if:**

- No backup confirmation
- Active incident on prod API/DB
- Plan to enable `clips` or `waha_vendor_intake` before API+ops review

---

## 15. Verification commands (read-only / post-apply)

```bash
# Migration tip (Supabase SQL)
SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version DESC LIMIT 5;

# API identity
curl -sS https://api.vergeo5.com/fingerprint | jq .git_sha

# Customer build
curl -sS https://vergeo5.com/en/health | jq .buildId

# Feature flags (no secrets)
# SELECT flag, enabled FROM feature_flags ORDER BY flag;

# RLS suite (staging/local only — NOT production)
cd services/api && uv run pytest tests/rls -q
```

---

_This plan does not authorize execution. Operator approval required for each wave._
