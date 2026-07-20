# Database backup runbook (CODE_COMPLETE)

Operational runbook for the **independent** nightly logical dump (pg_dump → gzip → OCI
Object Storage). Supabase dashboard / PITR backups are **additive** — they do **not**
satisfy the documented independent-backup requirement (D21 / G7 / `backup-schedule.md`).

| Field                              | Value                                                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Implementation status**          | **CODE_COMPLETE** (workflow JSON + scripts + validators in repo)                                           |
| **G7 (Backups and restore proof)** | **NOT PASS** — still requires one real dated OCI dump + timed restore evidence                             |
| Workflow                           | `infra/n8n/backup.json` (`active: false` until post-merge activation)                                      |
| Dump script                        | `infra/scripts/db-dump.sh`                                                                                 |
| Watchdog                           | `infra/scripts/db-backup-watchdog.sh`                                                                      |
| Restore                            | `infra/scripts/db-restore.sh` · drill: `infra/scripts/restore-drill.sh` / `scripts/ops/restore-staging.sh` |
| Schedule contract                  | `infra/n8n/backup-schedule.md`                                                                             |
| DR playbook                        | `docs/ops/runbook-disaster-recovery.md`                                                                    |
| Drill log                          | `docs/ops/drill-log.md`                                                                                    |

## What the workflow does

1. **Nightly dump** — cron `0 2 * * *` timezone `Africa/Lusaka` → SSH to OCI host →
   `infra/scripts/db-dump.sh`.
2. **Missed-schedule watchdog** — cron `0 4 * * *` Africa/Lusaka →
   `infra/scripts/db-backup-watchdog.sh` (fails if newest dump older than
   `BACKUP_MAX_AGE_HOURS`, default 26h).
3. **Manual / restore-drill mode** — `POST /webhook/backup-manual` with header
   `X-Backup-Secret` matching n8n `$env.BACKUP_WEBHOOK_SECRET` (timing-safe compare).
4. **On failure** — WhatsApp text to founder with **metadata only** (status, size,
   sha256 prefix, migration tip, redacted stderr). Never DSN / passwords / row data.
5. **Retry safety** — each run uses a unique UTC timestamped object name
   (`vergeo5-<UTC>.sql.gz`); retries create a new object, never overwrite/delete in-progress dumps.

## Backup artifact contract

Each successful run produces:

| Artifact                      | Contents                           |
| ----------------------------- | ---------------------------------- |
| `vergeo5-<UTC>.sql.gz`        | Plain `pg_dump` piped through gzip |
| `vergeo5-<UTC>.manifest.json` | Metadata (no secrets, no row data) |

Manifest fields:

- `timestamp_utc`
- `env_id` (`BACKUP_ENV_ID` / `ENV`)
- `backup_mode` (`scheduled` \| `manual` \| `drill`)
- `dump_name` / `object_key`
- `migration_tip` (latest `supabase_migrations.schema_migrations.version` or `unknown`)
- `size_bytes`
- `sha256`
- `retention_days`
- `status` (`success` \| `failure`)
- `error` (short, non-secret)

Stdout ends with `BACKUP_MANIFEST_JSON={...}` for n8n parsers.

## Encryption & independence

| Layer            | Mechanism                                                                 |
| ---------------- | ------------------------------------------------------------------------- |
| In transit (DB)  | `sslmode=require` appended for Supabase DSNs missing `sslmode`            |
| In transit (OCI) | OCI CLI HTTPS object put                                                  |
| At rest          | OCI Object Storage bucket encryption-at-rest; public access blocked       |
| Independence     | Logical dump in **our** OCI bucket — not solely provider dashboard backup |

## Retention

- Default **14 days** (`BACKUP_RETENTION_DAYS`, D21).
- Prune deletes **only** `db/vergeo5-*.sql.gz` and `db/vergeo5-*.manifest.json` under
  `OCI_OBJECT_PREFIX` (default `db/`) older than the retention window.
- Local dir (`BACKUP_LOCAL_DIR`, default `/var/backups/vergeo5`) pruned the same way.

## Credential & variable inventory (names only)

### n8n credentials (UI — never commit values)

| Credential name              | Type             | Used by                                                |
| ---------------------------- | ---------------- | ------------------------------------------------------ |
| `Vergeo5 OCI Host SSH`       | SSH private key  | SSH dump / watchdog nodes                              |
| `Vergeo5 WhatsApp Cloud API` | HTTP Header Auth | Alert HTTP nodes (same pattern as `admin-digest.json`) |

Committed JSON uses `"id": "REPLACE_WITH_CREDENTIAL_ID"` only.

### n8n `$env` (names only)

| Name                       | Purpose                                                  |
| -------------------------- | -------------------------------------------------------- |
| `BACKUP_WEBHOOK_SECRET`    | Manual webhook auth (`X-Backup-Secret`)                  |
| `WHATSAPP_CLOUD_API_URL`   | Graph messages endpoint                                  |
| `WHATSAPP_CLOUD_API_TOKEN` | Bearer for WhatsApp send                                 |
| `FOUNDER_WHATSAPP_TO`      | E.164 recipient for ops alerts                           |
| `BACKUP_MIN_BYTES`         | Optional; alert “too small” floor (script default 10240) |
| `VERGEO5_REPO_ROOT`        | Optional override; script default `/home/opc/vergeo5`    |

### Host / `infra/.env` (names only — values never in repo or workflow JSON)

| Name                    | Purpose                                           |
| ----------------------- | ------------------------------------------------- |
| `SUPABASE_DB_URL`       | Source Postgres for `pg_dump` (or `DATABASE_URL`) |
| `OCI_NAMESPACE`         | Object Storage namespace                          |
| `OCI_BUCKET_NAME`       | Independent backup bucket                         |
| `OCI_CLI_PROFILE`       | Optional; omit when using instance principal      |
| `OCI_OBJECT_PREFIX`     | Default `db/`                                     |
| `BACKUP_RETENTION_DAYS` | Default `14`                                      |
| `BACKUP_LOCAL_DIR`      | Default `/var/backups/vergeo5`                    |
| `BACKUP_ENV_ID` / `ENV` | Environment identifier in manifest                |
| `BACKUP_MODE`           | `scheduled` / `manual` / `drill`                  |
| `BACKUP_MIN_BYTES`      | Reject implausibly small dumps                    |
| `BACKUP_MAX_AGE_HOURS`  | Watchdog staleness (default `26`)                 |
| `SKIP_OCI_UPLOAD`       | `1` for local/drill runs without OCI              |

## Alert matrix

| Condition            | Detection                                    | Alert                   |
| -------------------- | -------------------------------------------- | ----------------------- |
| Backup failure       | non-zero SSH / `status=failure`              | WhatsApp ops alert      |
| Empty / too small    | `size_bytes < BACKUP_MIN_BYTES`              | script fails + alert    |
| Checksum / integrity | `gzip -t` fail / integrity error in manifest | script fails + alert    |
| Destination failure  | OCI put/list errors                          | script fails + alert    |
| Missed schedule      | watchdog age > max                           | watchdog cron → alert   |
| Workflow crash       | Error Trigger path                           | WhatsApp workflow error |

## Security rules

- Never log passwords, service-role keys, full connection strings, or row data.
- Do not paste dump contents into n8n, Slack, or this repo.
- Bucket IAM: deploy VM principal + founder break-glass only.

## Manual break-glass (host)

```bash
ssh opc@<OCI_VM_PUBLIC_IP>
cd ~/vergeo5
set -a && source infra/.env && set +a
export BACKUP_MODE=manual BACKUP_ENV_ID=production
bash infra/scripts/db-dump.sh
```

Verify (names/dates only):

```bash
oci os object list \
  --namespace "${OCI_NAMESPACE}" \
  --bucket-name "${OCI_BUCKET_NAME}" \
  --prefix "db/" \
  --sort-by timeCreated \
  --sort-order DESC \
  --limit 5
```

## Manual webhook (restore-drill trigger)

After import + activation of the production webhook URL:

```bash
curl -fsS -X POST "https://n8n.vergeo5.com/webhook/backup-manual" \
  -H "X-Backup-Secret: ${BACKUP_WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"drill"}'
```

Expect HTTP 200 with redacted stdout tail on success; 401 on bad secret; 500 on dump failure.

## Validation (repo)

```bash
bash scripts/ci/validate-backup-workflow.sh
# from services/api:
uv run pytest tests/test_n8n_registry.py tests/test_ops_n8n_01_audit.py tests/test_backup_workflow_artifact.py -q
```

## Post-merge activation

See the PR body for the exact import → configure → test → activate checklist.
Until a dated OCI object exists and a timed restore is logged in `docs/ops/drill-log.md`,
**do not mark G7 PASS**.
