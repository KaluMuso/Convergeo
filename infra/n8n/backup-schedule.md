# Nightly database backup schedule (n8n)

Documents how the **daily off-peak logical dump** is scheduled on the OCI n8n instance. Full workflow JSON export is owned by **M14** — this pebble defines the contract only.

## Schedule

| Field       | Value                                                                       |
| ----------- | --------------------------------------------------------------------------- |
| Cron        | `0 2 * * *` (02:00 Africa/Lusaka, daily)                                    |
| Timezone    | `Africa/Lusaka`                                                             |
| Script      | `infra/scripts/db-dump.sh` on the OCI VM                                    |
| Retention   | 14 days (`BACKUP_RETENTION_DAYS`, D21)                                      |
| Destination | OCI Object Storage `oci://${OCI_BUCKET_NAME}/db/vergeo5-<timestamp>.sql.gz` |

Off-peak avoids overlap with peak mobile-money traffic and Supabase maintenance windows.

## n8n workflow shape (M14 will export JSON)

1. **Cron trigger** — `0 2 * * *`, timezone `Africa/Lusaka`.
2. **Execute Command** node (or SSH to host) — runs:

```bash
cd /home/opc/vergeo5/infra
set -a && source .env && set +a
export BACKUP_RETENTION_DAYS=14
bash scripts/db-dump.sh
```

3. **IF** exit code ≠ 0 → **failure branch** (below).
4. **IF** success → optional Slack/email ping with object name + byte size (no connection strings).

### Required env on the VM (`infra/.env`)

| Name              | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| `SUPABASE_DB_URL` | Source database for `pg_dump`                        |
| `OCI_NAMESPACE`   | Object Storage namespace                             |
| `OCI_BUCKET_NAME` | Backup bucket (encryption-at-rest, no public access) |
| `OCI_CLI_PROFILE` | Optional; omit if using instance principal           |

`db-dump.sh` reads these at runtime — **never** embed values in the n8n workflow.

## Failure alerting

On non-zero exit from `db-dump.sh`:

1. n8n **Error Workflow** or IF branch sends alert to founder (WhatsApp/SMS/email — channels wired in M14).
2. Message template (no secrets):

   ```
   [Vergeo5] DB backup FAILED at {{ $now }}
   Host: n8n.vergeo5.com
   Check: docker compose logs n8n; ssh VM and run scripts/db-dump.sh manually
   ```

3. Log retention: n8n execution history ≥ 7 days for post-mortem.

Tie-in: M14 notification outbox will use the same founder contact routing as payment recon alerts.

## Manual run (break-glass)

```bash
ssh opc@<OCI_VM_PUBLIC_IP>
cd ~/vergeo5/infra
set -a && source .env && set +a
bash scripts/db-dump.sh
```

Verify upload:

```bash
oci os object list \
  --namespace "${OCI_NAMESPACE}" \
  --bucket-name "${OCI_BUCKET_NAME}" \
  --prefix "db/" \
  --sort-by timeCreated \
  --sort-order DESC \
  --limit 3
```

## Security

- Dumps may contain PII — bucket policy: deploy user + founder only.
- `db-dump.sh` redacts passwords in logs; do not enable n8n "include stdout" in alerts if it might echo env.
- Rotate OCI API keys via standard key rotation; update `~/.oci/config` on VM.

## Related

- `infra/scripts/db-dump.sh` — implementation
- `infra/ROLLBACK.md` — restore + app rollback
- `infra/n8n/README.md` — container ops
