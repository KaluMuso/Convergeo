# Deploy + migration truth (Prompt 6)

**Date (UTC):** 2026-07-20T15:08:27Z  
**Executor:** Cursor cloud agent (read-mostly; no production money / `public_launch` changes)  
**Supabase project:** `dpadrlxukcjbewpqympu` (Vergeo5, eu-north-1)  
**Master tip assessed:** `d9839db349887ab48a52c18546e05961a62498d6`  
(`Merge pull request #369 from KaluMuso/feat/customer-commerce-discovery`)

> **No fabricated success.** Migrations were **not** applied. Frontends were **not** promoted.  
> **`public_launch` / production collection gates:** unchanged (no `public_launch` key in `platform_config`; money tables empty).

---

## 1. Fingerprint summary (immutable IDs)

| Variable                             | Value                                                                     | Status                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `MASTER_SHA`                         | `d9839db349887ab48a52c18546e05961a62498d6`                                | Proved (`origin/master`)                                                         |
| `DEPLOYED_SHA_CUSTOMER`              | `cde40bf32763d14511deb72c59c1a7586867f93e`                                | Proved (Vercel prod `dpl_6Pgevsi44Cy8z5a2MWDKu9k2eRAo` + `/en/health` `buildId`) |
| `DEPLOYED_SHA_VENDOR`                | `5a4668a10291b3c381613975139431658c3c5be4`                                | Proved (Vercel prod `dpl_3qg4H35SxKbJKANJV4r2nDTAcTxa`)                          |
| `DEPLOYED_SHA_ADMIN`                 | `2f9971110797ca722dfb6a68e73a66955e0f714c`                                | Proved (Vercel prod `dpl_298135m42jAM3nDZAd68SptgWuTG`)                          |
| `DEPLOYED_API_DIGEST`                | **UNKNOWN / NOT_AUDITABLE**                                               | Live `api.vergeo5.com` → **502**; no OCI host inspect                            |
| `GHCR_LATEST_DIGEST` (registry only) | `sha256:c015e5a6dc2f77b0c52ff4cf37c6b582a41797bfaffe171b9774a00a1bd52758` | Tagged `latest` + `2f99711…` — **not** proof of host pull                        |
| `LIVE_MIGRATION_TIP`                 | `20260720074318` / `0063_revoke_execute_review_reply_guards`              | Proved (Supabase `schema_migrations`)                                            |

### Frontend lag vs master tip

| App      | Prod SHA         | Commits behind tip (high level)                                             |
| -------- | ---------------- | --------------------------------------------------------------------------- |
| customer | `cde40bf` (#366) | Missing #367 FORCE RLS (DB/API), #368 demo exclude, #369 commerce discovery |
| vendor   | `5a4668a` (#360) | Missing #361–#369 (docs/UI/money-adjacent FE + catalog)                     |
| admin    | `2f99711` (#368) | Missing #369 only (customer FE polish; low admin impact)                    |

---

## 2. Live migration ledger vs master tip

### 2.1 Last live-verified family (prior evidence)

VA-P02 (2026-07-19) applied `0051`/`0053`–`0056` to prod. Board (2026-07-20) later verified through live `0062` + live-only `0063_revoke…`.

### 2.2 Live tip (this session)

Latest row in `supabase_migrations.schema_migrations`:

- version `20260720074318`
- name `0063_revoke_execute_review_reply_guards`

Also present (timestamped MCP-style): `0051`–`0062` content names through `0062_payments_checkout_success_uniq`.  
Repo-prefix `0052` appears as timestamp `20260717100303` / name `0052_product_relations` (pre-existing skew).

### 2.3 Repo master migration files after live tip (content not on live)

| Repo file                                                      | Live status     | Notes                                                                                                           |
| -------------------------------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------- |
| `0065_refunds_source_key_uniq.sql` (#352 body, RC-02 renumber) | **NOT applied** | `refunds.source_key` column **absent**; `refunds_order_id_active_uniq` still present                            |
| `0064_force_rls_launch_tables.sql` (#367)                      | **NOT applied** | `ticket_type_instances` / `ticket_type_price_tiers` / `product_relations` have ENABLE RLS but **FORCE = false** |
| Live `0063_revoke_execute_review_reply_guards`                 | Applied live    | **Missing from `origin/master` files** (exists only on branch `claude/convergeo-bug-audit-nu1g4b` @ `9d146cc`)  |

### 2.4 Numbering collision (RC-02) — blocks naive apply

| Plane             | `0063` meaning                                                                           |
| ----------------- | ---------------------------------------------------------------------------------------- |
| Live ledger       | revoke EXECUTE on review-reply guards                                                    |
| Repo before RC-02 | `refunds.source_key` uniqueness (#352) occupied the `0063` prefix                        |
| Repo after RC-02  | `0063` matches live revoke; `0064` remains FORCE RLS; source_key is renumbered to `0065` |

**Do not** run `supabase db push` / apply repo `0063_*.sql` by filename against live.

---

## 3. Migration plan (not executed)

### Step 0 — Preconditions (all required)

1. **Recoverable backup verified** — dated OCI logical dump object listed **or** founder-confirmed Supabase backup/PITR artifact for `dpadrlxukcjbewpqympu`.  
   **This session:** `BLOCKED_EXTERNAL` (no OCI Object Storage list; no host SSH; workspace `SUPABASE_DB_URL` was a local leftover, not prod).
2. Land **RC-02 reconcile PR** on master: add `0063_revoke_execute_review_reply_guards.sql` (match live), keep `0064_force_rls_launch_tables.sql` as-is, renumber source_key → `0065_refunds_source_key_uniq.sql`, keep #352 SQL body unchanged.
3. Freeze money automations if any live money rows appear (currently `orders=payments=refunds=ledger=kyc=0`).

### Step A — `refunds_source_key` (content of #352)

| Aspect           | Detail                                                                                                                                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unapplied        | Yes                                                                                                                                                                                                   |
| Transaction      | Single migration transaction (MCP `apply_migration` / CLI)                                                                                                                                            |
| Locks / rewrites | `ALTER TABLE refunds ADD COLUMN`; `UPDATE` backfill (0 rows today); `NOT NULL`; `DROP INDEX refunds_order_id_active_uniq`; `CREATE UNIQUE INDEX … source_key` partial                                 |
| Data backfill    | `coalesce(breakdown->>'idempotency_key', 'refund-order-'\|\|order_id)` — **0 rows** now → trivial                                                                                                     |
| Rollback         | Documented in SQL comments: drop new index/column; recreate order unique from 0032                                                                                                                    |
| Forward-fix      | Prefer reconcile numbering then apply; **or** MCP apply with distinct ledger **name** `refunds_source_key_uniq` (timestamp version) **after** backup — still requires RC-02 for repo↔live CLI hygiene |
| Verify           | See §5 queries                                                                                                                                                                                        |

### Step B — FORCE RLS (`0064_force_rls_launch_tables`)

| Aspect        | Detail                                                        |
| ------------- | ------------------------------------------------------------- |
| Unapplied     | Yes                                                           |
| Transaction   | DDL only; idempotent ENABLE/FORCE                             |
| Locks         | Light ACCESS EXCLUSIVE on three tables (empty/small)          |
| Data backfill | None                                                          |
| Rollback      | `ALTER TABLE … NO FORCE ROW LEVEL SECURITY` (policies remain) |
| Verify        | `relforcerowsecurity = true` on the three tables              |

### Apply decision this session

**NOT APPLIED** — backup readiness precondition failed (`BLOCKED_EXTERNAL`).

---

## 4. Backup readiness

| Check                                       | Result                                                                       |
| ------------------------------------------- | ---------------------------------------------------------------------------- |
| Independent OCI dump list                   | **BLOCKED_EXTERNAL** — no OCI CLI credentials / host SSH in this environment |
| Prod `SUPABASE_DB_URL` for `db-dump.sh`     | **Unavailable** (not present as prod DSN)                                    |
| Supabase dashboard backup/PITR confirmation | **NOT_AUDITABLE** this session                                               |
| n8n `backup.json`                           | Repo CODE_COMPLETE on other PR; **not** live-activated; does not clear G7    |
| Historical VA-P00 founder backup            | Prior session claim only — **not re-verified**                               |

**Gate:** no live DDL until a recoverable backup is explicitly verified.

---

## 5. Verification queries (read-only results this session)

```text
refunds.source_key exists          = false
refunds_source_key_active_uniq     = false
refunds_order_id_active_uniq       = true
refunds/orders/payments/ledger/kyc = 0 / 0 / 0 / 0 / 0

FORCE RLS:
  order_money_gates, payments, refunds, orders, kyc_records = forced true
  ticket_type_instances, ticket_type_price_tiers, product_relations = forced false

payments_checkout_group_success_uniq index = present
custom_access_token_hook function          = present
order_money_gates table                    = present

platform_config: no public_launch / collections_enabled keys
  (cod_cap_ngwee=50000 etc. present — truncated in ops notes only)
```

---

## 6. Runtime probes (sanitised)

| Probe                                  | Result                                                                                                                     |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz`  | **502** (Caddy) — **FAILED**                                                                                               |
| `GET https://api.vergeo5.com/readyz`   | **502** — **FAILED**                                                                                                       |
| Customer `GET /en/health` (www)        | **200** `{"status":"ok","app":"customer","env":"production","buildId":"cde40bf…"}`                                         |
| Customer `/en/categories`              | **200** (~120KB, title Browse categories)                                                                                  |
| Customer `/en/c/*` category PLP        | **200** (sampled 5)                                                                                                        |
| Customer product PDP                   | **NOT SAMPLED** — no `/en/listing                                                                                          | product` hrefs in directory/search HTML (empty/demo-filtered catalogue) |
| Customer `/en/s/<uuid>` service detail | **200**                                                                                                                    |
| Customer `/en/checkout`                | **200**; honesty markers present (`invite`/`beta`/`not available`/`unavailable`); no payment-success false-success strings |
| Customer `/en/kyc`                     | **404** (no customer KYC page at that path)                                                                                |
| Vendor `/en/health`                    | **307** → login (auth-gated; JSON `{"redirect":…}`) — health SHA **not** publicly readable                                 |
| Vendor `/en/kyc`                       | **200** (login shell / gated)                                                                                              |
| Admin `/en/health`                     | **302** Cloudflare Access — health SHA **not** publicly readable without Access                                            |

---

## 7. Promote / redeploy

| Surface                      | Action taken | Reason                                                                             |
| ---------------------------- | ------------ | ---------------------------------------------------------------------------------- |
| Vercel customer/vendor/admin | **None**     | MCP `deploy_to_vercel` is file-upload, not git promote; no Vercel promote API used |
| OCI API container            | **None**     | **BLOCKED_EXTERNAL** — no host SSH; live API 502                                   |

**Required founder actions:**

1. Repair API on OCI (`docker compose ps`, logs, `redeploy-api.sh` pin to known GHCR digest).
2. Promote/redeploy Vercel production to `d9839db` (or latest master) for customer + vendor (+ admin if desired).
3. After backup: RC-02 reconcile → apply FORCE RLS (`0064`) → apply source_key (`0065`) → re-run §5.

---

## 8. Failed probes

1. API `healthz` / `readyz` → **502**
2. `DEPLOYED_API_DIGEST` host-side → **NOT_AUDITABLE**
3. Independent backup object list → **BLOCKED_EXTERNAL**
4. Product PDP probe → **not available** (no listing URLs in public HTML)
5. Vendor/admin public health JSON SHA → **auth/Access gated**
6. Migrations apply → **blocked** (backup + RC-02)

---

## 9. Remaining deployment blockers

1. **API down (502)** — blocks money, KYC API, readiness.
2. **Migration ledger collision + unapplied source_key + unapplied FORCE RLS.**
3. **Frontend prod behind master** (customer/vendor material lag).
4. **Backup/G7** — independent dump + restore evidence incomplete.
5. **GHCR tip:** `latest` = `2f99711`, not `d9839db` (frontend-only tip may not rebuild API — OK if API unchanged).

---

## 10. GO / NO-GO

### Recommendation: **NO-GO**

| Scope                          | Verdict                                                                                                                            |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Invite browse-beta (static FE) | **Conditional** — categories/home/checkout honesty OK on customer prod SHA, but **API 502** and catalog emptiness limit usefulness |
| Real-money / collections       | **NO-GO**                                                                                                                          |
| `public_launch`                | **NO-GO** (keep closed)                                                                                                            |
| Claim “live = master tip”      | **NO-GO** — FE lag + API digest unknown + migrations behind                                                                        |

---

## 11. Release-gates touch policy

Only update gate notes for checks **actually proved** in this document (frontend prod SHAs recorded; live migration tip recorded; API digest still FAIL/NOT_AUDITABLE; DB not at repo tip). Do **not** mark G7/G9 PASS.
