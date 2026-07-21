# Disaster-recovery runbook (M15-P09)

Incident playbook for Vergeo5 infrastructure loss. One section per failure domain, each
with a **trigger**, an **RTO/RPO target**, **exact copy-pasteable commands** (not prose),
and **verification**. Sibling docs handle the mechanics this runbook orchestrates:

- `infra/ROLLBACK.md` — app-deploy rollback + DB-restore mechanics (RTO/RPO basis).
- `infra/scripts/db-dump.sh` — nightly logical dump → gzip → OCI Object Storage (D21).
- `infra/scripts/db-restore.sh` — restore a gzip logical dump into a target DB.
- `infra/scripts/restore-drill.sh` — marker-level dump→wipe→restore self-test.
- `scripts/ops/restore-staging.sh` + `scripts/ops/restore-smoke.sql` — **this pebble**:
  schema-aware staging restore drill (core tables + seed data + migration currency).
- `infra/n8n/backup-schedule.md` · `infra/cloudflare-dns.md` · `infra/vercel.md` ·
  `infra/ENVIRONMENTS.md` — schedule, DNS, Vercel, and env inventory.

**Objectives (whole platform)**

| Metric  | Target        | Basis                                                              |
| ------- | ------------- | ----------------------------------------------------------------- |
| **RTO** | ≤ **30 min**  | App pin + compose restart, or restore latest dump + smoke verify. |
| **RPO** | ≤ **24 h**    | Nightly logical dump (02:00 Africa/Lusaka); worst case ~24h old.  |

> Backups contain **PII** (Zambia DPA). The OCI bucket is encryption-at-rest,
> public-access-blocked, IAM limited to the VM deploy user + founder break-glass.
> **No connection strings or secrets in this repo** — every command below reads
> credentials from the environment (`SUPABASE_DB_URL`, `VERCEL_TOKEN`, OCI CLI profile, …).

## Conventions used below

```bash
# All DB URLs come from the environment — NEVER hardcode. On the OCI VM:
cd /home/opc/vergeo5/infra && set -a && source .env && set +a
# Sanity: confirm which DB you are about to touch (password auto-redacted).
printf '%s\n' "$SUPABASE_DB_URL" | sed -E 's#(://[^:/]+:)[^@]+@#\1***@#'
```

## 0. First response (every incident)

```bash
# 1. Timestamp + declare in the founder ops log (solo founder still writes it down).
date -u +'INCIDENT START %Y-%m-%dT%H:%M:%SZ'
# 2. Capture current state for a clean rollback later.
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml ps
vercel ls vergeo5-customer --prod | head -5          # note current prod deployment id
curl -fsS -o /dev/null -w '%{http_code}\n' https://vergeo5.com/api/healthz || echo DOWN
# 3. Money safety: if the DB or payments are involved, FREEZE escrow release + payouts
#    BEFORE any restore (see §1 step A and §5). Never release escrow on unverified data.
```

---

## 1. Database loss or corruption (Supabase Postgres)

**Trigger:** Supabase DB unreachable-but-provider-up, data corruption, bad migration, or
an accidental destructive change. **RTO ≤ 30 min · RPO ≤ 24 h** (nightly dump; a few
minutes if Supabase PITR is available on the current plan).

### A. Freeze money movement first (mandatory)

```bash
# Defer auto-release timers so no escrow releases while data is in doubt (real config keys).
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" <<'SQL'
UPDATE public.platform_config SET value='100000' WHERE key='release_after_delivered_hours';
UPDATE public.platform_config SET value='100000' WHERE key='release_after_shipped_days';
SQL
# Pause the release/payout automations on the VM (idempotent — safe to re-run).
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml stop n8n
```

### B1. Preferred — Supabase point-in-time restore (if enabled on the plan)

```bash
# PITR is driven from the dashboard (plan-dependent feature):
#   Supabase → Project → Database → Backups → Point in Time → pick the timestamp
#   JUST BEFORE the incident → Restore. Confirm the project ref first:
supabase projects list                     # note the ref for $SUPABASE_PROJECT_ID
# After the dashboard restore completes, jump to step C to verify.
```

### B2. Fallback — restore the latest nightly logical dump from OCI

```bash
# Restores gzip logical dump into the target. The prod VM runs ENV=production, so the guard
# (db-restore.sh:is_prod_url) REQUIRES --force AND an interactive `RESTORE` confirmation — a bare
# `--latest` exits 1. This matches infra/ROLLBACK.md.
cd /home/opc/vergeo5/infra
SUPABASE_DB_URL="$SUPABASE_DB_URL" bash scripts/db-restore.sh --latest --force   # then type: RESTORE
# Or a specific object already downloaded:
SUPABASE_DB_URL="$SUPABASE_DB_URL" bash scripts/db-restore.sh --file /var/backups/vergeo5/vergeo5-<ts>.sql.gz --force
```

### C. Verify the restore (schema + seed + migrations current)

```bash
# Deep invariant check (core tables present, config seed non-empty, migration ledger).
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" -f /home/opc/vergeo5/scripts/ops/restore-smoke.sql
# Spot-check the newest data you expect to exist post-restore.
psql -tA "$SUPABASE_DB_URL" -c "SELECT max(created_at) FROM public.orders;"
```

### D. Reconcile BEFORE releasing money, then unfreeze

```bash
# Align payments/orders vs the Lenco ledger (M08 reconciliation) before any release.
# Then restore normal release timers and resume automations.
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" <<'SQL'
UPDATE public.platform_config SET value='48' WHERE key='release_after_delivered_hours';
UPDATE public.platform_config SET value='7'  WHERE key='release_after_shipped_days';
SQL
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml start n8n
date -u +'DB RESTORE VERIFIED %Y-%m-%dT%H:%M:%SZ'
```

---

## 2. OCI VM loss (api + caddy + n8n host)

**Trigger:** the Always-Free VM is unreachable/terminated. **RTO ≤ 30 min · RPO ≈ 0**
for the app (stateless API; source in git; secrets in the secret store) — n8n workflow
state (`n8n_data` volume) RPO ≤ 24 h and is non-critical automation.

```bash
# 1. Provision a fresh OCI Always-Free VM (Ubuntu), install Docker + compose plugin.
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker

# 2. Clone the repo and restore secrets from the secret store (NEVER from this repo).
git clone https://github.com/KaluMuso/Convergeo.git /home/opc/vergeo5
cd /home/opc/vergeo5/infra
cp /path/to/secret-store/vergeo5.env .env      # or: oci vault secret get ... > .env
chmod 600 .env

# 3. Bring the stack up (api → healthcheck-gated caddy → n8n) and wait for health.
docker compose up -d --build
docker compose ps
# api is expose-only (no host port mapping — only caddy publishes 80/443), so probe it
# from inside the container, mirroring the compose healthcheck.
for i in $(seq 1 30); do
  docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" && break; sleep 2; done

# 4. Point Cloudflare DNS at the new VM public IP (see infra/cloudflare-dns.md).
#    Update the A record for api.vergeo5.com → <new-vm-ip>, proxied (orange cloud).

# 5. (Optional) Restore n8n workflow state if the volume backup exists.
docker compose stop n8n
docker run --rm -v vergeo5_n8n_data:/data -v /var/backups/vergeo5:/b alpine \
  sh -c 'cd /data && tar xzf /b/n8n_data-<ts>.tgz'
docker compose start n8n
```

**Verify**

```bash
curl -fsS https://api.vergeo5.com/healthz && echo OK
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml ps   # api healthy, caddy up
```

---

## 3. Supabase provider outage (DB intact, provider down)

**Trigger:** Supabase status page reports an incident; DB unreachable but **not** lost.
**RTO = provider ETA** (external, not owned) · **RPO 0** (no data lost).

```bash
# 1. Confirm it is the provider, not us.
curl -fsS -o /dev/null -w '%{http_code}\n' https://status.supabase.com/api/v2/status.json
psql "$SUPABASE_DB_URL" -c 'SELECT 1' || echo 'DB unreachable — provider-side'

# 2. Serve a friendly maintenance state instead of 5xx (customer app on Vercel).
#    Toggle the maintenance banner/flag (env var read at the edge — no code deploy):
vercel env add MAINTENANCE_MODE production <<<'on'
vercel redeploy vergeo5-customer --prod

# 3. Do NOT attempt a restore — data is intact. Poll and monitor.
watch -n 30 'psql "$SUPABASE_DB_URL" -c "SELECT 1" && echo RECOVERED'

# 4. On recovery: clear maintenance, run the smoke check, resume automations.
vercel env rm MAINTENANCE_MODE production --yes && vercel redeploy vergeo5-customer --prod
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" -f /home/opc/vergeo5/scripts/ops/restore-smoke.sql
```

---

## 4. Vercel outage (customer app host)

**Trigger:** Vercel edge/build outage; the customer app (SSR/ISR/SEO) is unavailable.
Vendor/admin apps run on OCI/Caddy and are unaffected. **RTO ≤ 15 min · RPO 0.**

```bash
# 1. Confirm the outage scope.
curl -fsS -o /dev/null -w '%{http_code}\n' https://www.vercel-status.com/api/v2/status.json
curl -fsS -o /dev/null -w '%{http_code}\n' https://vergeo5.com

# 2. Fastest: fail over at Cloudflare to a static maintenance page (no origin needed).
#    Cloudflare → Rules → (or) Workers → serve maintenance HTML for vergeo5.com.
#    See infra/cloudflare-dns.md for the exact zone + record ids.

# 3. If the outage is prolonged, redeploy the last known-good build once Vercel returns:
vercel ls vergeo5-customer --prod | head -5
vercel rollback <last-green-deployment-url> --yes

# 4. Verify.
curl -fsS -o /dev/null -w '%{http_code}\n' https://vergeo5.com   # expect 200
```

---

## 5. Lenco outage (payment provider) — degraded mode

**Trigger:** Lenco MoMo collections / card widget / webhooks are failing. **RTO = provider
ETA** (external) · **RPO 0** — payment webhooks are **idempotent** and Lenco **retries
30 min × 24 h**, so confirmations replay on recovery with no data loss.

**Degraded mode = COD + nationwide pickup CONTINUE; escrow releases FROZEN.**
COD and pickup never touch Lenco, so they keep working with no change. Money safety:
**no escrow release without a Lenco confirmation** — releases stay frozen until Lenco is
back and reconciliation is clean (never pay a vendor on an unconfirmed collection).

```bash
# 1. Freeze escrow releases + payouts (defer auto-release timers; pause automations).
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" <<'SQL'
UPDATE public.platform_config SET value='100000' WHERE key='release_after_delivered_hours';
UPDATE public.platform_config SET value='100000' WHERE key='release_after_shipped_days';
SQL
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml stop n8n   # halts release/payout jobs

# 2. Keep COD + pickup open. COD stays within the K500 policy cap (do NOT raise it):
psql -tA "$SUPABASE_DB_URL" -c "SELECT key,value FROM public.platform_config WHERE key='cod_cap_ngwee';"
#    -> expect 50000 ngwee (K500). COD (method='cod') and nationwide pickup checkout are
#       unaffected because they do not call Lenco. New online MoMo/card 'initiate' calls
#       will fail fast at the Lenco adapter — that is safe (idempotent, retried on recovery).

# 3. Communicate: WhatsApp/status banner — "Mobile-money & card temporarily unavailable;
#    pay cash on delivery (≤K500) or reserve for pickup." (maintenance flag as in §3 step 2).

# 4. Monitor Lenco, then RECOVER: confirmations replay automatically via retries.
curl -fsS -o /dev/null -w '%{http_code}\n' https://api.lenco.co/access/v2/  # provider probe
#    On recovery: resume automations, run reconciliation, THEN restore release timers.
docker compose -f /home/opc/vergeo5/infra/docker-compose.yml start n8n
# ...run M08 reconciliation until payments/orders align with the Lenco ledger...
psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" <<'SQL'
UPDATE public.platform_config SET value='48' WHERE key='release_after_delivered_hours';
UPDATE public.platform_config SET value='7'  WHERE key='release_after_shipped_days';
SQL
```

---

## Scenario summary

| # | Scenario                     | Trigger                              | RTO      | RPO    | Recovery path (this runbook) |
|---|------------------------------|--------------------------------------|----------|--------|------------------------------|
| 1 | DB loss / corruption         | DB corrupt / bad migration / drop    | ≤ 30 min | ≤ 24 h | Freeze → PITR or `db-restore.sh --latest` → `restore-smoke.sql` → recon → unfreeze |
| 2 | OCI VM loss                  | VM terminated / unreachable          | ≤ 30 min | ≈ 0    | Re-provision → clone → `.env` from vault → `docker compose up` → DNS |
| 3 | Supabase provider outage     | Provider incident, DB intact         | provider | 0      | Maintenance mode → monitor → smoke on recovery |
| 4 | Vercel outage                | Edge/build outage (customer app)     | ≤ 15 min | 0      | Cloudflare maintenance failover → redeploy last-green |
| 5 | Lenco outage                 | MoMo/card/webhooks failing           | provider | 0      | Freeze escrow/payouts → **COD + pickup continue** → replay on recovery |

**Drill cadence:** the restore drill (`scripts/ops/restore-staging.sh`) is run **manually**
(founder/staging-gated — there is no CI/n8n scheduler wired for it yet); results are logged in
`docs/ops/drill-log.md`. The live ≤30-minute staging restore is the target to demonstrate.
