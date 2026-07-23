# Live probe + gap report — 2026-07-23

**Probe time (UTC):** 2026-07-23T17:00Z  
**Master tip:** `d591ef518980381aa75cd23f86e06e8990f7adbc` (`fix(customer): locale 404 catch-all + ops migration 0070 evidence #503`)  
**Supersedes:** July 20 go/no-go live column where newer probes disagree  
**Companions:** `docs/production-readiness/2026-07-20/go-no-go-report.md`, `docs/plan/launch-checklist.md`, `scripts/ops/verify_live.sh`

---

## Executive summary

**Recommendation: still NO_GO for real-money / public launch** — but the **deploy plane improved materially** since the July 20 audit:

| Area                               | July 20                 | July 23                                         |
| ---------------------------------- | ----------------------- | ----------------------------------------------- |
| API `api.vergeo5.com`              | **502**                 | **200** (`/healthz`, `/readyz`, `/fingerprint`) |
| Customer prod SHA                  | Behind tip              | **Matches master** (`d591ef5`)                  |
| DB migration tip                   | `0063` (repo at `0064`) | **70/70** — repo tip applied                    |
| FORCE RLS on ticket tiers          | **false**               | **true** (0064 applied)                         |
| `commission_snapshot` immutability | Missing                 | **Applied** (0069, this probe)                  |
| `vendor.commercial_tier`           | Missing                 | **Applied** (0070, 2026-07-23)                  |

**Remaining blockers** are unchanged in kind: founder/legal gates (F2, F4, F9b, F5…), live execution proofs (E2E, load, DR, Sentry, money drill), API deploy fingerprint (`GIT_SHA=unknown`), n8n workflows inactive, and small code hardening pebbles (CR-A…CR-E).

---

## 1. `verify_live.sh` matrix (production probes)

Command: `bash scripts/ops/verify_live.sh` (repo at `d591ef5`)

| Gate    | Status   | Detail                                                                                          |
| ------- | -------- | ----------------------------------------------------------------------------------------------- |
| **G0**  | SKIP     | `SUPABASE_DB_URL` unset in agent env                                                            |
| **G1**  | **PASS** | API healthz/readyz 200; search RPC ok; env=production; customer/vendor/admin surfaces reachable |
| **L12** | **PASS** | `GET /search?q=phone` → total=9, degraded=false                                                 |
| **G2**  | SKIP     | `CHECK_LOCALHOST!=1`                                                                            |
| **G3**  | SKIP     | Needs F9b + `MONEY_DRILL_REPORT`                                                                |
| **G4**  | SKIP     | Playwright staging run                                                                          |
| **G5**  | SKIP     | `N8N_API_KEY` unset                                                                             |
| **G6**  | SKIP     | Sentry DSNs + smoke report                                                                      |
| **G7**  | SKIP     | OCI backup drill                                                                                |
| **G8**  | SKIP     | GitHub branch-protection audit                                                                  |
| **G9**  | **FAIL** | `fingerprint.git_sha=unknown` vs master `d591ef5` — API container missing `GIT_SHA` / image tag |

**Overall:** FAIL (G9 only — infra config, not outage).

---

## 2. Fingerprint table

| #   | Surface              | Result                                                        | Evidence                                                             |
| --- | -------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------- |
| 1   | Master SHA           | `d591ef518980381aa75cd23f86e06e8990f7adbc`                    | `git rev-parse HEAD`                                                 |
| 2   | Customer prod        | **MATCH** `d591ef5`                                           | `GET https://www.vergeo5.com/en/health` → 200                        |
| 3   | Vendor prod          | **UNKNOWN** (auth-gated)                                      | `GET /en/health` → 307 → login; buildId not readable without session |
| 4   | Admin prod           | **UNKNOWN** (CF Access)                                       | `/en/health` → 302 Cloudflare Access                                 |
| 5   | API health           | **UP**                                                        | `/healthz` `{"status":"ok"}`; `/readyz` search_rpc=ok                |
| 6   | API fingerprint      | env=production, ref=dpadrlxukcjbewpqympu, **git_sha=unknown** | `GET /fingerprint`                                                   |
| 7   | Live migration count | **70**                                                        | Supabase `schema_migrations`                                         |
| 8   | Repo migration count | **70** (tip `0070`)                                           | `supabase/migrations/`                                               |
| 9   | `0069` trigger       | **Present**                                                   | `orders_commission_snapshot_immutable` on `orders`                   |
| 10  | `0070` column        | **Present**                                                   | `vendors.commercial_tier` nullable + CHECK                           |

### RLS / FORCE RLS (live sample — improved vs July 20)

| Table                   | RLS  | FORCE RLS |
| ----------------------- | ---- | --------- |
| ticket_type_instances   | true | **true**  |
| ticket_type_price_tiers | true | **true**  |
| product_relations       | true | **true**  |
| vendors                 | true | **true**  |

### Flags (live)

| Flag                 | Enabled   |
| -------------------- | --------- |
| `public_launch`      | **false** |
| `zamtel_collections` | **false** |

### Catalogue / money (live)

| Metric                               | Count                                    |
| ------------------------------------ | ---------------------------------------- |
| `vendor_listings` active             | 134 (all demo-tagged images)             |
| `GET /catalog/listings` consumer PLP | **0 items** (demo exclusion — by design) |
| `GET /search?q=phone`                | **9 hits**                               |
| payments / orders / ledger           | **0**                                    |

---

## 3. What improved since July 20

1. **API restored** — no longer 502; search and readiness probes green.
2. **Customer promoted to master tip** — includes locale 404 fix (#503).
3. **Migration drift closed** — live DB now at repo tip (70 migrations); 0064–0070 applied including FORCE RLS and commission immutability.
4. **404 UX** — unknown locale routes return branded 404 (not 500).

---

## 4. Remaining gaps (beyond API redeploy / F9b / G6 / G7)

### Tier 0 — deploy / ops (founder or creds)

| Gap                                 | Why it blocks                                             | Owner                                                          |
| ----------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| API `GIT_SHA` / image tag on deploy | G9 FAIL; cannot prove API code version                    | Ops — set `GIT_SHA` + `API_IMAGE_TAG` in Hetzner env, redeploy |
| Vendor/admin SHA parity             | Unknown vs master; vendor DNS may still be miswired       | Founder — `vercel_promote.sh` + DNS per staging notes          |
| n8n workflows **0 active**          | Notifications, reconciliation crons, error alerts dormant | Founder — publish + activate 3 Wave-A workflows                |
| `0051` role-sync hook               | JWT custom claims may be stale vs `user_roles`            | Apply + verify auth hook enabled in Supabase dashboard         |
| Beta invite cohort                  | No production cohort created                              | Founder — seed `beta_invites` for controlled beta              |
| Deploy + rollback demonstrated      | M01 staging proof unchecked                               | Ops — runbook execution + evidence link                        |
| CSP report-only                     | Not enforced on customer                                  | Post-launch hardening per M15-P03 runbook                      |

### Tier 1 — live execution proofs (code exists, run needed)

| Proof                       | Script / doc                                    | Gate         |
| --------------------------- | ----------------------------------------------- | ------------ |
| E2E vs Lenco sandbox        | `e2e/` + Playwright on staging                  | G4 / M16-P07 |
| Load p95 &lt;500ms @100cc   | `scripts/load/` k6                              | M16-P08      |
| Restore ≤30min              | `scripts/ops/restore-staging.sh` on OCI         | G7 / M15-P09 |
| Sentry capture + alert      | `scripts/ops/sentry_smoke.sh`                   | G6 / M16-P06 |
| Staging money drill         | `scripts/drills/lenco_sandbox_money_drill.py`   | G3 / F9b     |
| `verify_live.sh` full green | Needs `SUPABASE_DB_URL`, `N8N_API_KEY`, reports | CR-E         |

### Tier 2 — founder / legal (hard NO_GO)

| Gate                                | Status                |
| ----------------------------------- | --------------------- |
| F2 PACRA + TPIN                     | Open                  |
| F4 Counsel (NPS Act escrow)         | Open — pre-real-money |
| F9b Lenco sandbox + production keys | Open                  |
| F5 WhatsApp templates approved      | Open                  |
| F6–F8, vergeo5.co.zm                | Open / follow-up      |
| Section 0 founder GO sign-off       | **Unchecked**         |

### Tier 3 — code pebbles (`prompts/fixes/`)

| ID         | Gap                                                      |
| ---------- | -------------------------------------------------------- |
| **CR-A**   | `/sell` commission table static — needs public rates API |
| **CR-B**   | bem/nya missing namespaces; zh not public                |
| **CR-C**   | Search degraded-mode banner + FTS fallback UX            |
| **CR-D/E** | Lenco drill + deploy-verify runbook closure              |

### Tier 4 — known scaffold / non-blocking

- i18n flat keys still render raw in some surfaces (`nav.home`, `shop.home` on vendor 404).
- Legal pages marked pending F4 review.
- All seeded listings are demo inventory → consumer PLP empty until real vendor listings exist (expected for invite-only beta).

---

## 5. Recommended next actions (ordered)

1. **API redeploy** with `GIT_SHA=d591ef5` (or current master) — clears G9.
2. **Promote vendor/admin** to master + confirm vendor DNS on Vercel project.
3. **Activate n8n** notification + reconciliation + error workflows.
4. **Founder:** F9b sandbox creds → staging money drill → E2E green.
5. **Founder:** F4 counsel + F2 PACRA before any real-money flag flip.
6. **Optional code wave:** CR-A commission endpoint, CR-C search resilience.

---

## 6. Agent actions this session

- Ran `verify_live.sh` against production.
- Applied **`0069_orders_commission_snapshot_immutable`** on Supabase `dpadrlxukcjbewpqympu` (was the sole missing migration; live count now 70/70).
- Verified trigger `orders_commission_snapshot_immutable` present.

**Do not** treat this report as founder GO — Section 0 of `launch-checklist.md` remains unsigned.
