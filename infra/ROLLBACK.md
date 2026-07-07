# Vergeo5 rollback runbook

Operational rollback for **application deploys** and **database restores**. Targets align with M15-P09 disaster-recovery drills.

| Metric                     | Target           | Basis                                                            |
| -------------------------- | ---------------- | ---------------------------------------------------------------- |
| **RTO** (recovery time)    | ≤ **30 minutes** | App pin + compose restart, or restore latest dump + smoke checks |
| **RPO** (data loss window) | ≤ **24 hours**   | Nightly logical dump (D21); last good dump may be up to ~24h old |

Backups contain **PII** — OCI Object Storage bucket must use encryption-at-rest, block public access, and limit IAM to the VM deploy user + founder break-glass only.

---

## Before any rollback

1. **Announce** in the founder ops channel (even solo — write it down with timestamp).
2. **Capture state:** note current Vercel deployment ID, `docker compose ps`, and latest backup object name in OCI.
3. **Payment/escrow freeze (DB restore only):** coordinate with **M08 reconciliation** — pause Lenco webhook processing and hold manual payouts until restore is verified. After restore, run recon to align `payments`, `orders`, and Lenco ledger before releasing escrow.

---

## Path A — Application rollback (no DB restore)

Use when the API or OCI-served apps regressed but the database is healthy.

### A1. Customer app (Vercel)

```bash
# List recent production deployments (requires vercel CLI + VERCEL_TOKEN)
vercel ls vergeo5-customer --prod

# Promote previous known-good deployment (replace <deployment-url>)
vercel rollback <deployment-url> --yes

# Or via dashboard: Project → Deployments → … on last green build → Promote to Production
```

Verify:

```bash
curl -fsS https://vergeo5.com/api/healthz || curl -fsS https://<customer-domain>/en
```

### A2. API + Caddy + n8n (OCI VM)

SSH to the VM, pin the previous image/build, and recreate containers.

```bash
ssh opc@<OCI_VM_PUBLIC_IP>
cd ~/vergeo5/infra

# Record current state
docker compose ps
git log -1 --oneline

# Pin API to previous commit (example — use the last known-good SHA/tag)
git fetch origin
git checkout <KNOWN_GOOD_SHA>

# Rebuild API image from pinned source; Caddy/n8n use pinned tags in compose
docker compose build api
docker compose up -d

# Smoke checks
docker compose ps
curl -fsS https://api.vergeo5.com/healthz
curl -fsS https://api.vergeo5.com/readyz
```

**Vendor/admin** standalone processes (if running on host ports 3001/3002): restart from the same pinned git SHA.

```bash
# Example — adjust paths to your process manager
cd ~/vergeo5
git checkout <KNOWN_GOOD_SHA>
pnpm install --frozen-lockfile
pnpm build --filter vendor --filter admin
# restart vendor/admin systemd units or pm2 processes
```

### A3. Roll forward again

After fix lands on `master`, redeploy Vercel production and on the VM:

```bash
cd ~/vergeo5/infra
git checkout master && git pull
docker compose build api
docker compose up -d
```

---

## Path B — Database restore from backup

Use when Postgres data is corrupted, deleted, or must be rewound. **Destructive** — overwrites the target database.

### B1. Preconditions

- [ ] Escrow/payment reconciliation coordinated (M08) — webhooks paused, no payouts in flight.
- [ ] Application traffic drained or API scaled to maintenance (return 503 from Caddy or stop API container).
- [ ] `oci` CLI authenticated on VM (`OCI_CLI_PROFILE` or instance principal).
- [ ] Env on VM includes `SUPABASE_DB_URL` (or `DATABASE_URL`), `OCI_NAMESPACE`, `OCI_BUCKET_NAME`.

### B2. List available dumps

```bash
oci os object list \
  --namespace "${OCI_NAMESPACE}" \
  --bucket-name "${OCI_BUCKET_NAME}" \
  --prefix "db/" \
  --sort-by timeCreated \
  --sort-order DESC \
  --limit 5 \
  ${OCI_CLI_PROFILE:+--profile "${OCI_CLI_PROFILE}"}
```

### B3. Restore latest dump (production)

```bash
cd ~/vergeo5/infra
export ENV=production   # triggers prod guard

# Requires --force and typing RESTORE at prompt
bash scripts/db-restore.sh --latest --force
```

Or restore a specific file:

```bash
bash scripts/db-restore.sh \
  --file /var/backups/vergeo5/vergeo5-20260706T020000Z.sql.gz \
  --force
```

Target URL comes from `SUPABASE_DB_URL` / `DATABASE_URL` in `infra/.env`. Override with `--target-url` only for drills/staging.

### B4. Post-restore verification

```bash
# API health after restore
docker compose up -d api
curl -fsS https://api.vergeo5.com/readyz

# Spot-check critical tables (examples — adjust when schema exists)
psql "${SUPABASE_DB_URL}" -c "SELECT count(*) FROM orders WHERE created_at > now() - interval '1 day';"
```

### B5. Reconcile payments (M08)

1. Compare Lenco dashboard settlements vs `payments` / `payment_events` since backup timestamp.
2. Replay idempotent webhook handlers for missed events (Lenco retries up to 24h).
3. Resolve stuck escrow states before re-enabling payouts.
4. Document actions in the incident log.

### B6. Resume traffic

```bash
docker compose up -d
# Re-enable Vercel production if it was rolled back separately
```

---

## Monthly restore drill (staging)

Run on staging or locally to prove RTO:

```bash
cd infra
bash scripts/restore-drill.sh
# Expect: PASS restore-drill (duration=<N>s, marker=...)
```

Log output in `docs/ops/drill-log.md` (M15-P09).

---

## Environment variables (names only)

| Variable                           | Used by       | Purpose                                      |
| ---------------------------------- | ------------- | -------------------------------------------- |
| `SUPABASE_DB_URL` / `DATABASE_URL` | dump, restore | Postgres connection (never log)              |
| `OCI_NAMESPACE`                    | dump, restore | Object Storage namespace                     |
| `OCI_BUCKET_NAME`                  | dump, restore | Backup bucket                                |
| `OCI_CLI_PROFILE`                  | dump, restore | Optional OCI CLI profile                     |
| `BACKUP_LOCAL_DIR`                 | dump, restore | Local spool (default `/var/backups/vergeo5`) |
| `BACKUP_RETENTION_DAYS`            | dump          | Prune age (default `14`)                     |
| `OCI_OBJECT_PREFIX`                | dump, restore | Key prefix (default `db/`)                   |
| `SKIP_OCI_UPLOAD`                  | dump          | `1` = local-only (drills)                    |
| `ENV`                              | restore       | `production` triggers prod guard             |

---

## Related

- `infra/scripts/db-dump.sh` — nightly logical backup
- `infra/scripts/db-restore.sh` — guarded restore
- `infra/scripts/restore-drill.sh` — automated round-trip test
- `infra/n8n/backup-schedule.md` — n8n cron wiring (M14 owns workflow JSON)
