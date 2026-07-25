# Nightly database backup schedule (n8n)

Documents how the **daily off-peak logical dump** is scheduled on the OCI n8n instance.

**Workflow JSON:** `infra/n8n/backup.json` (ships `active: false`).  
**Runbook:** `docs/ops/backup-runbook.md` · **Restore drill:** `docs/ops/backup-restore-drill.md`.

**Status:** **CODE_COMPLETE** in repo; imported into the live n8n instance **inactive** on
2026-07-23 (see [Live n8n import & activation](#live-n8n-import--activation)). **G7 PASS**
still requires a real dated OCI dump + timed restore evidence (see restore-drill doc) —
importing the workflow does **not** satisfy G7. Provider dashboard / PITR alone does **not**
satisfy the independent-backup requirement either.

## Schedule

| Field       | Value                                                                       |
| ----------- | --------------------------------------------------------------------------- |
| Cron        | `0 2 * * *` (02:00 Africa/Lusaka, daily)                                    |
| Watchdog    | `0 4 * * *` (missed-schedule check)                                         |
| Timezone    | `Africa/Lusaka` (workflow `settings.timezone`)                              |
| Script      | `infra/scripts/db-dump.sh` on the OCI VM (via SSH from n8n)                 |
| Retention   | 14 days (`BACKUP_RETENTION_DAYS`, D21)                                      |
| Destination | OCI Object Storage `oci://${OCI_BUCKET_NAME}/db/vergeo5-<timestamp>.sql.gz` |

Off-peak avoids overlap with peak mobile-money traffic and Supabase maintenance windows.

## Live n8n import & activation

Imported into the live instance on **2026-07-23** (personal project), **inactive** — no
schedule fires and the webhook is idle until it is activated.

| Field        | Value                                                                                     |
| ------------ | ----------------------------------------------------------------------------------------- |
| Workflow     | `Vergeo5 — Database Backup`                                                               |
| Workflow ID  | `OAdOD4kmIbSNehkJ`                                                                        |
| URL          | `https://n8n.vergeo5.com/workflow/OAdOD4kmIbSNehkJ`                                       |
| Manual drill | `POST https://n8n.vergeo5.com/webhook/58ecfba1-66ee-494c-a07e-378c38e683e8/backup-manual` |
| State        | `active: false` (never published)                                                         |

Reproduced faithfully from `backup.json` — the redaction regexes (all three Code nodes) and
the `crypto.timingSafeEqual` webhook-auth check were byte-verified against source. Minor, safe
deviations from the JSON: node `typeVersion`s bumped to instance-current releases; alert-message
assembly rewritten from template literals to string concatenation (identical output); the
`sha256` truncation marker `…` → `...`. The n8n-generated `webhookId` differs from the JSON's
fixed value, so the manual-drill URL above is the authoritative one.

### Activation checklist (founder-only)

1. **Credentials** (both absent from n8n — create, then attach):
   - `Vergeo5 OCI Host SSH` (SSH Private Key) → the 3 SSH nodes. Holds the OCI VM key.
   - `Vergeo5 WhatsApp Cloud API` (Header Auth) → the 3 WhatsApp HTTP Request nodes.
2. **n8n instance env:** `WHATSAPP_CLOUD_API_URL`, `WHATSAPP_CLOUD_API_TOKEN`,
   `FOUNDER_WHATSAPP_TO`, `BACKUP_WEBHOOK_SECRET`, optional `BACKUP_MIN_BYTES` (default 10240).
3. **OCI VM env** (`infra/.env`, see table below): `SUPABASE_DB_URL`, `OCI_NAMESPACE`,
   `OCI_BUCKET_NAME`, `OCI_CLI_PROFILE` (or instance principal), `BACKUP_RETENTION_DAYS`.
4. **Two settings the SDK import cannot set — set them in the workflow Settings panel before activating:**
   - **Timezone → `Africa/Lusaka`** (otherwise the cron fires at 02:00 in the instance TZ).
   - **Error Workflow → this workflow** (so `Error Trigger` catches its own failures; the inline
     IF / continue-on-fail WhatsApp alert paths work regardless).
5. **G7 evidence:** activate → fire the manual drill (header `X-Backup-Secret: <BACKUP_WEBHOOK_SECRET>`)
   → confirm a dated `db/vergeo5-<ts>.sql.gz` in the bucket → timed restore per
   `docs/ops/backup-restore-drill.md`. That evidence — not the import — flips G7 to PASS.

## n8n workflow shape (`backup.json`)

1. **Cron Nightly Dump** — `0 2 * * *`, timezone `Africa/Lusaka`.
2. **SSH** to OCI host (credential `Vergeo5 OCI Host SSH`) — runs:

```bash
cd "${VERGEO5_REPO_ROOT:-/home/opc/vergeo5}"
set -a && source infra/.env && set +a
export BACKUP_MODE=scheduled
bash infra/scripts/db-dump.sh
```

3. **IF** exit code ≠ 0 → WhatsApp founder alert (metadata only).
4. **Cron Missed-Schedule Watchdog** — `0 4 * * *` → `infra/scripts/db-backup-watchdog.sh`.
5. **Webhook Manual Backup** — `POST /webhook/backup-manual` + `X-Backup-Secret` vs
   `$env.BACKUP_WEBHOOK_SECRET` for restore drills.

> n8n runs in Docker without `pg_dump`/`oci` on the container PATH; SSH to the host is
> the approved execution path (Execute Command on the n8n container is insufficient).

### Required env on the VM (`infra/.env`)

| Name              | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| `SUPABASE_DB_URL` | Source database for `pg_dump`                        |
| `OCI_NAMESPACE`   | Object Storage namespace                             |
| `OCI_BUCKET_NAME` | Backup bucket (encryption-at-rest, no public access) |
| `OCI_CLI_PROFILE` | Optional; omit if using instance principal           |

`db-dump.sh` reads these at runtime — **never** embed values in the n8n workflow.
Full name inventory: `docs/ops/backup-runbook.md`.

## Failure alerting

On non-zero exit from dump or watchdog:

1. IF branch → Code node (redact) → HTTP WhatsApp to `$env.FOUNDER_WHATSAPP_TO`.
2. Message includes status, reasons, env_id, dump name, size, sha256 prefix, migration tip —
   **no** connection strings or secrets.
3. Log retention: n8n execution history ≥ 7 days for post-mortem.

## Manual run (break-glass)

```bash
ssh opc@<OCI_VM_PUBLIC_IP>
cd ~/vergeo5
set -a && source infra/.env && set +a
bash infra/scripts/db-dump.sh
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
- `db-dump.sh` redacts passwords in logs; alerts strip DSNs / Bearer tokens.
- Rotate OCI API keys via standard key rotation; update `~/.oci/config` on VM.

## Related

- `infra/n8n/backup.json` — importable workflow
- `infra/scripts/db-dump.sh` · `db-backup-watchdog.sh` · `db-restore.sh`
- `docs/ops/backup-runbook.md` · `docs/ops/backup-restore-drill.md`
- `infra/ROLLBACK.md` — restore + app rollback
- `infra/n8n/README.md` — container ops
