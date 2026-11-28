# Production database backups on Cloudflare R2 (live path)

This is the live backup design. It replaces the OCI Object Storage path described in
`backup-runbook.md` (kept for history; `infra/scripts/db-dump.sh` is still used by the nightly
CI restore drill and is untouched). Supabase's own backups are not available on the Free plan,
so this independent copy is the only production backup.

| Field | Value |
| ----- | ----- |
| Script | `infra/scripts/db-backup-r2.sh` (installed on the host as `/usr/local/bin/vergeo5-db-backup`) |
| Schedule | `infra/cron/vergeo5-backup.cron`, timezone Africa/Lusaka |
| Where | Cloudflare R2 bucket `convergeo-backups`, prefixes `db/daily/`, `db/weekly/`, `db/manual/`, `db/drill/` |
| Format | `pg_dump -Fc`, streamed into GPG, so no plaintext dump touches disk |
| RPO / RTO | at most 12 hours of data (twice daily) / 30 minutes (target, proven by the monthly drill) |

## Schedule

| Job | When (Lusaka) | Prefix |
| --- | --- | --- |
| Daily backup | 02:00 and 14:00 | `db/daily/` |
| Weekly copy | Sunday 03:30 | `db/weekly/` |
| Weekly restore drill (throwaway Postgres) | Sunday 04:30 | result marker in `db/drill/` |
| Monthly timed restore onto staging | first Saturday, supervised | log entry in `docs/ops/drill-log.md` |
| Freshness watchdog (n8n, email) | hourly; alerts when the newest `db/daily/` object is 14 hours old or more | n/a |

## Retention and expiry (every rule is at least 30 days)

The bucket lock keeps every object for 30 days, so lifecycle rules must never expire sooner.

| Prefix | Expire after | Why |
| --- | --- | --- |
| `db/daily/` | 35 days | five days beyond the 30-day lock |
| `db/weekly/` | 120 days | about 17 weekly copies for slow-discovered damage |
| `db/manual/` | 60 days | ad-hoc dumps before risky changes |
| `db/drill/` | 90 days | drill history |

Cost: each encrypted dump is about 1.3 MB today. Roughly 70 daily plus 17 weekly plus a few manual
copies is under 300 MB, inside the R2 free tier (10 GB). Expected cost is $0 per month; recheck if the
database passes 1 GB.

## Keys and custody

- Backups are encrypted to a public GPG key. The private key is held offline by the founder.
- The server holds only the public key, so a stolen bucket or R2 token cannot read a backup.
- The R2 token on the server is scoped to this one bucket (Object Read and Write; R2 has no write-only token).
- The weekly automatic drill must decrypt. Decision needed (default: option A):
  - **A (recommended).** Add a second recipient, an on-host drill key (`BACKUP_EXTRA_FPR`). Anyone who
    already controls the host can read the database through its connection string, so this adds little
    risk, and the drill proves the real restore path every week. Bucket-only leaks stay unreadable.
  - **B.** No drill key. The weekly drill only checks size, checksum and recipient, and the full restore
    is manual each month with the offline key. Safer against host compromise, weaker proof.

## Restore (real incident)

Follow `runbook-disaster-recovery.md` section 1 (freeze money first). In place of step B2:

```bash
# Download the newest object (names only here; keys come from /root/vergeo5-backup.env).
aws --endpoint-url "$R2_ENDPOINT" s3 cp "s3://$R2_BUCKET/db/daily/<object>.dump.gpg" .
sha256sum -c <object>.dump.gpg.sha256
gpg --decrypt -o restore.dump <object>.dump.gpg      # needs the offline private key
pg_restore --no-owner --no-privileges -d "$TARGET_DB_URL" restore.dump
psql -v ON_ERROR_STOP=1 "$TARGET_DB_URL" -f scripts/ops/restore-smoke.sql
```

Dumps do not contain Storage files (KYC documents, order evidence) or custom-role passwords.
Storage files need a separate copy; see the follow-up list below.

## Drill evidence

Append every drill to `docs/ops/drill-log.md` (date, source object name, target, timings, PASS/FAIL).
Launch gate G7 passes only after one timed restore of a real R2 object is logged there.

## Follow-ups not done in this change

- Weekly copy of the Supabase Storage buckets (about 240 kB today).
- A second watchdog check on `db/drill/` that alerts if no passing drill marker exists for 9 days.
- Remove the OCI path (`db-dump.sh`, `infra/n8n/backup.json`, validators and tests) once nothing depends on it.
