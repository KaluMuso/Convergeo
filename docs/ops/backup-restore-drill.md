# Backup restore-drill procedure

Controlled procedure to prove that an **independent** logical dump can be restored
within RTO. Complements `docs/ops/runbook-disaster-recovery.md` and the append-only
log at `docs/ops/drill-log.md`.

| Gate                           | Status                                                             |
| ------------------------------ | ------------------------------------------------------------------ |
| Workflow + scripts in repo     | **CODE_COMPLETE**                                                  |
| G7 — Backups and restore proof | **NOT PASS** until a real dump + timed restore are evidenced below |

A local marker drill (`infra/scripts/restore-drill.sh`) or historical local PASS in
`drill-log.md` is useful engineering evidence but **does not** clear G7 for production.

## Preconditions

1. `infra/n8n/backup.json` imported; host can run `infra/scripts/db-dump.sh`.
2. OCI bucket credentials / instance principal working on the VM.
3. A **non-production** restore target URL in env (`TARGET_DB_URL` / scratch project).
4. Money automations understood — never restore over prod without the DR freeze steps.

## A. Produce a drill dump (choose one)

### A1. Host (recommended for first proof)

```bash
ssh opc@<OCI_VM_PUBLIC_IP>
cd ~/vergeo5
set -a && source infra/.env && set +a
export BACKUP_MODE=drill BACKUP_ENV_ID=staging   # or production for prod dump
bash infra/scripts/db-dump.sh
# Record object name + size + sha256 from BACKUP_MANIFEST_JSON= line (no DSN).
```

### A2. n8n manual webhook

```bash
curl -fsS -X POST "https://n8n.vergeo5.com/webhook/backup-manual" \
  -H "X-Backup-Secret: ${BACKUP_WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"drill"}'
```

Confirm execution success in n8n and that a new `db/vergeo5-*.sql.gz` (+ manifest)
appears in the OCI bucket.

### A3. Local only (no OCI — does not count for G7)

```bash
export SUPABASE_DB_URL='postgresql://…'   # local/scratch only
export SKIP_OCI_UPLOAD=1
export BACKUP_LOCAL_DIR=/tmp/vergeo5-backups
export BACKUP_MIN_BYTES=256
export BACKUP_MODE=drill
bash infra/scripts/db-dump.sh
```

## B. Timed restore into scratch

Prefer `scripts/ops/restore-staging.sh` (schema + seed + migration currency) or
`infra/scripts/db-restore.sh` for a gzip logical dump.

```bash
# Example: restore latest downloaded dump into a scratch DB (never prod URL without --force).
date -u +'RESTORE_DRILL_START %Y-%m-%dT%H:%M:%SZ'
SUPABASE_DB_URL="$TARGET_DB_URL" bash infra/scripts/db-restore.sh --file /path/to/vergeo5-<ts>.sql.gz
psql -v ON_ERROR_STOP=1 "$TARGET_DB_URL" -f scripts/ops/restore-smoke.sql
date -u +'RESTORE_DRILL_END %Y-%m-%dT%H:%M:%SZ'
```

Optional integrity check before restore:

```bash
sha256sum -c <(echo "<sha256_from_manifest>  vergeo5-<ts>.sql.gz")
gzip -t vergeo5-<ts>.sql.gz
```

## C. Record evidence

Append an entry to `docs/ops/drill-log.md` using the template there:

- Operator, source object key (name only), target env name (not URL)
- Timings: dump / restore / smoke / **TOTAL**
- Smoke result (tables / seed / migration tip)
- Explicit **PASS** or **FAIL**

## D. G7 checklist (founder)

- [ ] Nightly (or manual) dump object listed in OCI with timestamp within RPO (≤ 24h)
- [ ] Manifest present with sha256 + migration_tip + size_bytes
- [ ] Failure alert proven once (forced non-zero or bad secret path)
- [ ] Timed restore into scratch documented in `drill-log.md` with TOTAL ≤ RTO (30 min)
- [ ] Only then flip G7 evidence — **not** claimed by this CODE_COMPLETE PR

## Related

- `docs/ops/backup-runbook.md` — schedule, credentials (names), alerts
- `infra/n8n/backup-schedule.md` — cron contract
- `docs/ops/runbook-disaster-recovery.md` — production incident restore
