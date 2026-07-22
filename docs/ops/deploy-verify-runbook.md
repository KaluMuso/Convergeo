# Deploy, verify, and rollback runbook

**Purpose:** single authoritative path from `master` tip → verified live surfaces →
rollback-tested. Pair with the non-destructive verifier
[`scripts/ops/verify_live.sh`](../../scripts/ops/verify_live.sh) and gate definitions in
[`docs/production-readiness/2026-07-18/consolidated/release-gates.md`](../production-readiness/2026-07-18/consolidated/release-gates.md)
(G0–G9).

**Constraints:** read-only against production data except where an explicit apply/deploy
step is documented. Never print secrets. Outbound HTTPS from Cursor Cloud agents goes
through the egress proxy — see `/root/.ccr/README.md` on the VM (or `docs/ops/ci.md` for
local shells).

**Related:** `infra/ROLLBACK.md` · `docs/ops/runbook-disaster-recovery.md` ·
`docs/ops/supabase-workflow.md` · `docs/ops/n8n-activation-runbook.md` ·
`docs/ops/backup-runbook.md` · `docs/plan/launch-checklist.md` §3

---

## 0. Preconditions

| Item                     | Check                                                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Branch                   | Deploy from `master` tip (or a tagged release SHA recorded in the evidence pack).                                                                         |
| Credentials (names only) | `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD`, `SUPABASE_PROJECT_ID`, `VERCEL_TOKEN`, OCI SSH, `N8N_API_KEY`, GHCR pull on VM — values from vault only. |
| Backup (G7)              | Dated OCI dump **or** Supabase PITR window confirmed **before** any prod migration apply.                                                                 |
| Maintenance              | Announce in founder ops channel; note start time.                                                                                                         |
| Verifier                 | `bash scripts/ops/verify_live.sh` (or `--dry-run`) after each phase.                                                                                      |

Record evidence under `docs/production-readiness/<date>/` or the launch checklist §3 slots.

---

## 1. Migration apply (Supabase)

### 1.1 Repo migration ledger (source of truth)

As of master tip, the repo ships **68** additive files:

`supabase/migrations/0001_extensions.sql` … `0068_search_query_facets_wholesale_and_kinds.sql`

**Historical prod gap (2026-07-20 audit):** live was behind on
`0051_custom_access_token_role_hook`, `0053_translation_overrides`,
`0054_service_reviews`, `0055_service_bookable`, `0056_kyc_integrity`, plus everything
after the then-live tip (`0063` revoke … `0068`). Live had already applied `0052` under a
timestamp-style version key — reconcile via `schema_migrations` **names**, not replay
count alone. See `docs/production-readiness/2026-07-20/deploy-migration-truth.md`.

**Always reconcile before apply:**

```bash
# On a linked machine (interactive link once):
supabase link --project-ref <SUPABASE_PROJECT_ID>

# Read-only: list applied versions (no writes)
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version;"

# Compare to repo filenames:
ls -1 supabase/migrations/*.sql | sed 's|.*/||;s/_.*//'
```

Outstanding set = repo prefixes **minus** applied versions. At minimum, confirm the
historical gap files above are either applied or intentionally deferred with a written
waiver.

### 1.2 Pre-apply `db diff` (required)

Prove the linked remote matches expectations **before** pushing new SQL.

```bash
cd /path/to/vergeo5

# Ensure local stack matches repo (CI oracle)
supabase db reset --no-seed

# Diff linked remote → local (read-only on remote; generates a file only if drift exists)
supabase db diff --linked -f pre_apply_audit_$(date -u +%Y%m%d)

# Review output under supabase/migrations/pre_apply_audit_*.sql
# - Empty / "No schema changes" → safe to push pending numbered migrations only.
# - Unexpected drops or renames → STOP; reconcile with DBA (MR-S01 / RC-02).
```

**Do not commit** ad-hoc `pre_apply_audit_*` files unless they become an intentional
migration PR.

### 1.3 Pre-migration backup (G7 gate)

1. Trigger manual dump: `docs/ops/backup-runbook.md` (`backup-manual` webhook or
   `infra/scripts/db-dump.sh` on the OCI host).
2. Record OCI object name + `migration_tip` from manifest JSON.
3. Only then proceed.

### 1.4 Apply in order

Apply **only** migrations not yet in `schema_migrations`, in numeric order:

| Order | File                                     | Notes                                                                                               |
| ----- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1     | `0051_custom_access_token_role_hook.sql` | Auth hook SQL is **dormant** until enabled in Supabase Dashboard — see `docs/ops/role-sync-hook.md` |
| 2     | `0053_translation_overrides.sql`         |                                                                                                     |
| 3     | `0054_service_reviews.sql`               |                                                                                                     |
| 4     | `0055_service_bookable.sql`              |                                                                                                     |
| 5     | `0056_kyc_integrity.sql`                 | KYC integrity guards                                                                                |
| 6     | `0057` … `0068`                          | Apply every newer file through repo tip in order                                                    |

```bash
# Non-interactive push (after link + env)
export SUPABASE_ACCESS_TOKEN=...   # from vault
export SUPABASE_DB_PASSWORD=...    # from vault

supabase db push

# Post-apply read-only verify
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version DESC LIMIT 5;"
bash scripts/ops/verify_live.sh   # G0/G9 migration rows
```

**FORCE RLS (G0):** after `0064_force_rls_launch_tables.sql` applies, confirm:

```sql
SELECT c.relname, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
    'ticket_type_instances',
    'ticket_type_price_tiers',
    'product_relations'
  );
```

All three must show `relforcerowsecurity = true`.

### 1.5 Migration rollback

Supabase migrations are **forward-only** in prod. Rollback options:

| Scenario                   | Action                                                                              | RTO target  |
| -------------------------- | ----------------------------------------------------------------------------------- | ----------- |
| Bad migration mid-apply    | Stop push; restore DB from pre-apply backup (`infra/scripts/db-restore.sh --force`) | ≤ 30 min    |
| Bad migration already live | Restore backup taken in §1.3; redeploy prior API if code depended on new schema     | ≤ 30 min    |
| Reversible additive fix    | Ship a **new** numbered migration — never edit shipped files                        | next deploy |

Full DB restore playbook: `infra/ROLLBACK.md` Path B · `docs/ops/runbook-disaster-recovery.md`.

---

## 2. API deploy (OCI — Compose: api / caddy / n8n)

Host layout: `infra/docker-compose.yml` on the OCI VM (`~/vergeo5/infra` or
`/home/opc/vergeo5/infra`). API image: `ghcr.io/kalumuso/convergeo-api:${API_IMAGE_TAG}`.

### 2.1 Deploy

```bash
ssh opc@<OCI_VM_HOST>
cd ~/vergeo5

# Record current state for rollback (G9)
git fetch origin && git rev-parse --short HEAD | tee /tmp/pre-deploy-api-sha.txt
docker compose -f infra/docker-compose.yml ps
docker inspect ghcr.io/kalumuso/convergeo-api:latest --format '{{.Id}}' \
  | tee /tmp/pre-deploy-api-digest.txt

# Pin to master tip (or explicit SHA)
git checkout master && git pull --ff-only
export API_IMAGE_TAG="$(git rev-parse --short HEAD)"   # or full SHA

cd infra
docker compose pull api
docker compose up -d api caddy

# Env reload requires recreate — restart alone does NOT reload infra/.env
# bash /root/redeploy-api.sh   # if present on host
```

Required env names (values in `infra/.env` only): `SUPABASE_URL`, `SUPABASE_*_KEY`,
`SUPABASE_DB_URL` (session pooler **5432**), `ENV`, `CORS_ORIGINS`, internal `INTERNAL_*`
tokens — see `infra/.env.example`.

### 2.2 Verify API

```bash
curl -fsS "https://api.vergeo5.com/healthz"
curl -fsS "https://api.vergeo5.com/health"
curl -fsS "https://api.vergeo5.com/readyz"    # expect {"status":"ok","search_rpc":"ok",...}
curl -fsS "https://api.vergeo5.com/fingerprint" # env + git_sha + supabase_project_ref — no secrets

bash scripts/ops/verify_live.sh
```

`/readyz` shape (CR-C):

```json
{
  "status": "ok",
  "search_rpc": "ok",
  "search_embedding": "ok"
}
```

- Overall `status=degraded` → Supabase unreachable **or** `search_rrf` RPC failing — **page**.
- `search_embedding=degraded` alone (with `status=ok`) → `OPENROUTER_API_KEY` missing/invalid;
  keyword search still works — **warn**, do not treat as API down. See
  `infra/uptimerobot.md` monitor #6.

`/readyz` returning `status: degraded` usually means `SUPABASE_DB_URL` is blank/wrong (API falls
back to local DSN). Fix env and **recreate** the container.

### 2.3 API rollback (≤ 30 min drill)

| Step | Command / action                                                    | Minutes |
| ---- | ------------------------------------------------------------------- | ------- |
| 1    | Announce + note failing SHA/digest                                  | 2       |
| 2    | `export API_IMAGE_TAG=<KNOWN_GOOD_SHA>`                             | 1       |
| 3    | `docker compose pull api && docker compose up -d api caddy`         | 5       |
| 4    | `curl -fsS https://api.vergeo5.com/healthz && curl -fsS .../readyz` | 2       |
| 5    | `bash scripts/ops/verify_live.sh` — G1/G9 PASS                      | 5       |
| 6    | Log evidence in `docs/ops/drill-log.md`                             | 5       |

If schema and code diverged, pair with §1.5 DB restore. Details: `infra/ROLLBACK.md` Path A2.

---

## 3. Vercel frontends + DNS

Three projects (git-connected, root dirs under `apps/`):

| App      | Vercel project (typical)                  | Production host      | Health probe                             |
| -------- | ----------------------------------------- | -------------------- | ---------------------------------------- |
| Customer | `convergeo-customer` / `vergeo5-customer` | `www.vergeo5.com`    | `GET /en/health`                         |
| Vendor   | `convergeo-vendor`                        | `vendor.vergeo5.com` | `GET /en/health`                         |
| Admin    | `convergeo-admin`                         | `admin.vergeo5.com`  | `GET /en/health` (403 w/ CF Access = OK) |

### 3.1 Promote

```bash
# From deploy host with VERCEL_TOKEN
vercel ls vergeo5-customer --prod
vercel ls convergeo-vendor --prod
vercel ls convergeo-admin --prod

# Promote master deployment (or rollback — see §3.3)
vercel deploy --prod   # per project, from repo root with correct --cwd
```

Ensure env vars on each project: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
`NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`, `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` (customer).

### 3.2 DNS (Cloudflare)

| Record      | Target              | Proxy                                         | Notes                                             |
| ----------- | ------------------- | --------------------------------------------- | ------------------------------------------------- |
| `@` / `www` | Vercel CNAME        | Proxied                                       | Customer                                          |
| `vendor`    | Vercel vendor CNAME | Proxied                                       | Domain must be **added** to vendor Vercel project |
| `admin`     | Vercel admin CNAME  | DNS-only until cert, then Proxied + CF Access | See `docs/ops/admin-access.md`                    |
| `api`       | OCI VM A record     | DNS-only (grey)                               | TLS via Caddy on VM                               |

Verify:

```bash
dig +short www.vergeo5.com
dig +short vendor.vergeo5.com
dig +short admin.vergeo5.com
curl -fsS -o /dev/null -w "%{http_code}\n" "https://www.vergeo5.com/en/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "https://vendor.vergeo5.com/en/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "https://admin.vergeo5.com/en/health"
```

Update API `CORS_ORIGINS` on OCI when vendor/admin origins change.

### 3.3 Vercel rollback (≤ 30 min drill)

| Step | Action                                                        | Minutes |
| ---- | ------------------------------------------------------------- | ------- |
| 1    | `vercel ls <project> --prod` — copy last green deployment URL | 3       |
| 2    | `vercel rollback <deployment-url> --yes` per app              | 5       |
| 3    | Re-hit `/en/health` on all three hosts                        | 3       |
| 4    | `verify_live.sh` G1/G9 frontend SHA rows                      | 5       |
| 5    | Log drill                                                     | 5       |

---

## 4. n8n workflow activation

Registry: `docs/ops/n8n-workflows.md` · activation detail:
`docs/ops/n8n-activation-runbook.md`.

**Wave A (safe — activate after API `/readyz` is ok):**

| Workflow file                | Endpoint                             | Token env                          |
| ---------------------------- | ------------------------------------ | ---------------------------------- |
| `notification-dispatch.json` | `/internal/dispatch/tick`            | `INTERNAL_DISPATCH_TOKEN`          |
| `reconciliation.json`        | `/internal/reconciliation/*`         | `INTERNAL_RECONCILIATION_TOKEN`    |
| `reservation-sweeper.json`   | `/internal/stock-sweeper/tick`       | `INTERNAL_STOCK_SWEEPER_TOKEN`     |
| `embeddings-cron.json`       | `/internal/embeddings/tick`          | `INTERNAL_EMBEDDINGS_TOKEN`        |
| `admin-digest.json`          | `/internal/digest`                   | `INTERNAL_DIGEST_TOKEN`            |
| `analytics-retention.json`   | `/internal/analytics/retention-tick` | `INTERNAL_ANALYTICS_TOKEN`         |
| `backup.json`                | SSH → `infra/scripts/db-dump.sh`     | SSH + `BACKUP_WEBHOOK_SECRET` (G7) |

**Wave B — HELD** until Lenco sandbox money path (F9b) **and** counsel F4: `release-job`,
`order-jobs`, `event-release`, `tickets-issue`, `tickets-release`, money sweeper paths.

Per workflow:

1. `openssl rand -hex 32` → set matching `INTERNAL_*_TOKEN` in `infra/.env`.
2. Recreate API container (not mere restart).
3. Import JSON from `infra/n8n/` at `https://n8n.vergeo5.com`, bind `X-Internal-Token`
   credential, toggle **Active**, confirm first execution `success`.
4. Wrong token must return **401**, not **503** (unset token).

Confirm live:

```bash
# With N8N_API_KEY from n8n Settings → API
curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "https://n8n.vergeo5.com/api/v1/workflows?active=true" | jq '.data | length'

bash scripts/ops/verify_live.sh   # G5 row
```

### 4.1 n8n rollback

| Step | Action                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------ |
| 1    | Deactivate failing workflow in n8n UI (or unpublish via API).                                    |
| 2    | For money ticks, stop Wave B first: `docker compose stop n8n` halts all schedules (DR playbook). |
| 3    | Re-import last known-good JSON from `infra/n8n/` git SHA.                                        |
| 4    | Re-run `verify_live.sh` G5.                                                                      |

---

## 5. End-to-end verify + gate matrix

After all phases:

```bash
cd /path/to/vergeo5
export EXPECTED_ENV=production          # or staging
export MASTER_GIT_SHA="$(git rev-parse HEAD)"
export API_BASE_URL=https://api.vergeo5.com
# Optional read-only DB + n8n:
export SUPABASE_DB_URL=...              # session pooler, read-only role preferred
export N8N_API_KEY=...

bash scripts/ops/verify_live.sh
```

Gate mapping (full criteria in `release-gates.md`):

| Gate | Verifier check                                                                                                                         |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------- |
| G0   | Migrations include `0064`; FORCE RLS true on three launch tables (needs `SUPABASE_DB_URL`)                                             |
| G1   | `/healthz` `/health` `/readyz` HTTP 200; `readyz.status=ok`; customer/vendor health 200; **warn** if `search_embedding=degraded` alone |
| G2   | No `localhost:3001` / `localhost:8000` in customer HTML (optional `CHECK_LOCALHOST=1`)                                                 |
| G3   | **SKIP** in verifier — requires Lenco sandbox money drill                                                                              |
| G4   | **SKIP** — requires staging Playwright                                                                                                 |
| G5   | n8n active workflow count ≥ Wave A minimum; sample internal tick returns 401 not 503                                                   |
| G6   | **SKIP** — requires Sentry test event + UptimeRobot fire                                                                               |
| G7   | **SKIP** — requires dated OCI backup artifact + restore drill log                                                                      |
| G8   | **SKIP** — CI / branch-protection audit                                                                                                |
| G9   | `fingerprint.git_sha` matches `MASTER_GIT_SHA`; migration tip matches repo; deploy SHAs recorded                                       |

---

## 6. ≤ 30 min combined restore drill checklist

Use for launch checklist §3 "Deploy + rollback demonstrated" and G9 evidence.

| #   | Step                                                                       | Owner   | Done |
| --- | -------------------------------------------------------------------------- | ------- | ---- |
| 1   | Record pre-drill API digest, Vercel deployment IDs, DB migration tip       | Ops     | [ ]  |
| 2   | Roll back **customer** Vercel deploy to previous green (`vercel rollback`) | Ops     | [ ]  |
| 3   | Confirm `www.vergeo5.com/en/health` 200                                    | Ops     | [ ]  |
| 4   | Roll forward customer to current master                                    | Ops     | [ ]  |
| 5   | Pin API `API_IMAGE_TAG` to previous SHA; `docker compose up -d api`        | Ops     | [ ]  |
| 6   | Confirm `/healthz` + `/readyz` 200                                         | Ops     | [ ]  |
| 7   | Roll forward API to master tip                                             | Ops     | [ ]  |
| 8   | Run `verify_live.sh`; archive PASS/FAIL matrix                             | Ops     | [ ]  |
| 9   | Total elapsed ≤ 30 minutes (wall clock)                                    | Founder | [ ]  |

DB restore drill is separate (G7) — `scripts/ops/restore-staging.sh` on scratch DB only;
never point at production `postgres` without `infra/scripts/db-restore.sh` guards.

---

## 7. Troubleshooting

| Symptom                     | Likely cause                        | Fix                                             |
| --------------------------- | ----------------------------------- | ----------------------------------------------- |
| API 502                     | Caddy upstream down / container OOM | `docker compose ps`; check `dmesg`; redeploy §2 |
| `/readyz` degraded          | Missing `SUPABASE_DB_URL`           | Set session pooler DSN; recreate API            |
| `/fingerprint` env mismatch | Wrong `ENV` in `infra/.env`         | Fix + recreate                                  |
| Migration push fails        | Duplicate prefix / drift            | `migration-replay.sh`; RC-02 reconcile          |
| n8n tick 503                | Token unset                         | Set `INTERNAL_*` + recreate API                 |
| Vendor 404                  | Domain not on Vercel project        | Add domain in Vercel + DNS §3.2                 |

---

_Last updated: deploy-verify runbook (CR-E). Migration count tracks `supabase/migrations/`
on master tip — re-run `ls supabase/migrations/*.sql | wc -l` after new merges._
