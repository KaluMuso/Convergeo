# Wave 1 — Dispatch Runbook (VM-A · Deployment & Schema Truth)

**Date:** 2026-07-19 · **Mode:** founder-executed (all 5 pebbles are `[OPS]`) · **Plan:** D30 hybrid live-beta.
**Prompts:** `prompts/VA-P00…VA-P04-*.md` (full spec + acceptance per pebble). This is the ordered cover-sheet.

## Guardrails (do NOT)
- Do **not** flip `public_launch` or enable prepaid/`zamtel_collections` — real money stays OFF (D30/NB-13).
- Do **not** apply migrations to **production** in this wave — VA-P02 is **staging-first on a throwaway DB branch**; the prod apply is a later pebble (VC-P01) after the staging drill + backup.
- Do **not** run any migration before **VA-P00 backup** exists.
- Redact PII / payment refs / tokens in every evidence doc; secrets stay in env/dashboards, never in the repo.

## Access needed
| System | For | Have? |
| ------ | --- | ----- |
| Supabase dashboard / CLI (`SUPABASE_DB_URL`) | VA-P00 backup, VA-P02 branch+migrate | founder |
| Vercel (team `vergeo-projects`) | VA-P01 promote, VA-P04 env | founder |
| API host (Hetzner SSH) + GHCR read | VA-P03 image pin | founder |

## Execution order (dependencies)
```
VA-P00 backup ──┬── blocks ──▶ VA-P02 migrations (staging branch)
                │
   (independent, run in parallel):  VA-P01 promote FE ─▶ VA-P04 env
                                    VA-P03 pin API image
```
Do VA-P00 first. Then VA-P02, VA-P01, VA-P03 in parallel; VA-P04 after VA-P01.

---

## ① VA-P00 — Pre-migration backup  *(blocks VA-P02)*  · prompt `VA-P00`
- **Do:** full logical dump (or trigger a platform PITR snapshot).
  ```bash
  pg_dump "$SUPABASE_DB_URL" -Fc -f vergeo5-$(date -u +%Y%m%d).dump
  pg_restore --list vergeo5-$(date -u +%Y%m%d).dump | head     # proves restorable shape
  sha256sum vergeo5-$(date -u +%Y%m%d).dump
  ```
- **Verify:** `pg_restore --list` non-empty; sha256 recorded; timestamp **before** VA-P02.
- **Evidence:** `evidence/backup-YYYYMMDD.md` (location + size + sha256 + UTC time; no secrets/PII).

## ② VA-P02 — Apply migrations 0051/0053–0056 (staging-first)  · prompt `VA-P02`
- **Do:** create a **throwaway DB branch** (Supabase branch or local `supabase db reset`), then apply in order:
  `0051` → `0053` → `0054` → `0055` → `0056`. Reconcile the `0052` version-key skew (live carries `20260717100303`) with the DBA before applying so replay doesn't collide.
- **Verify (on the branch):** `custom_access_token*` fn (0051) · `translation_overrides` table (0053) · `service_reviews` cols (0054) · `services.bookable` (0055) · `guard_kyc_record_integrity` trigger + view (0056); legacy `kyc pending→submitted` handled. Run `scripts/ci/migration-replay.sh` (duplicate-prefix guard) + the `db`/`rls` jobs green.
- **Evidence:** `evidence/migrations-apply.md` (branch `schema_migrations` head + object checks). **Prod untouched.**

## ③ VA-P01 — Promote frontends to master tip  · prompt `VA-P01`
- **Do:** on Vercel, promote `convergeo-customer` / `-vendor` / `-admin` to the current `master` tip; record each `dpl_…` id + `githubCommitSha`.
- **Verify:**
  ```bash
  for l in en fr zh; do curl -sS -m15 -o /dev/null -w "$l %{http_code}\n" https://www.vergeo5.com/$l/categories; done  # want 200, NOT 500/digest 3012388270
  curl -sS -m15 -o /dev/null -w "vendor %{http_code}\n" https://vendor.vergeo5.com/en/health
  curl -sS -m15 -o /dev/null -w "admin %{http_code}\n"  https://admin.vergeo5.com/en/health
  ```
- **⚠ Known blocker:** the Vercel **free-tier daily deploy quota is currently exhausted** (`api-deployments-free-per-day` — seen on PR CI). A production redeploy may be rate-limited until the ~24h reset. Retry after reset, or upgrade the plan if you need it sooner.
- **Evidence:** `evidence/deploy-promote.md` (3 SHAs + categories probe).

## ④ VA-P03 — Pin & redeploy API image  · prompt `VA-P03`
- **Do:** read the GHCR digest for `ghcr.io/kalumuso/convergeo-api` at the master-tip build; set `API_IMAGE_TAG`; `infra/redeploy-api.sh`; restart behind Caddy.
- **Verify:**
  ```bash
  curl -sS -m15 https://api.vergeo5.com/healthz
  curl -sS -m15 -o /dev/null -w "%{http_code}\n" -X POST https://api.vergeo5.com/admin/kyc/00000000-0000-0000-0000-000000000000/start-review  # 401/403 = route EXISTS (not 404)
  ```
- **Evidence:** `evidence/api-image.md` (digest recorded; KYC lifecycle routes live).

## ⑤ VA-P04 — Set vendor-app URL env  *(after VA-P01)*  · prompt `VA-P04`
- **Do:** set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer` (Production) and **rebuild** (a `NEXT_PUBLIC_*` var is inlined at build — a restart won't do).
- **Verify:**
  ```bash
  curl -sS -m15 https://www.vergeo5.com/en/sell | grep -o 'https://vendor\.vergeo5\.com[^"]*' | head   # CTA href present
  curl -sS -m15 https://www.vergeo5.com/en/sell | grep -c 'temporarily unavailable'                   # want 0
  ```
- **Evidence:** `evidence/cta.md`.

---

## Report back (for my Phase-4 review)
Paste each pebble's **IMPLEMENTATION REPORT** (STATUS / FILES / DEVIATIONS / TESTS / EXCERPTS / QUESTIONS — the block at the end of each `VA-P0x` prompt). I'll review money/authz/RLS/idempotency with heightened scrutiny, update `docs/plan/00-status.md` + `release-gates.md`, and green-light Wave 2 (money-sandbox + n8n) which per D30 can run in parallel.

**Wave 1 exit = live == repo:** 3 frontends on tip (categories 200), migrations verified on the staging branch, API image pinned (KYC routes live), CTA env set. Still **no real money, `public_launch=false`.**
