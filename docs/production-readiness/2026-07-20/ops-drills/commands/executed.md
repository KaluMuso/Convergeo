# Commands executed (Prompt 10)

## Preflight

- `curl https://api.vergeo5.com/{healthz,readyz,fingerprint}` → 502
- `n8n search_workflows query=backup` → count 0
- `ls infra/n8n/backup.json` → ABSENT
- Supabase SQL: migration tip, feature_flags.public_launch=false, money table counts
- Vercel `list_deployments` for convergeo-{customer,vendor,admin}

## Restore (isolated only)

- `sha256sum` vs manifest for `/tmp/vergeo5-backups-ci/vergeo5-20260720T150434Z.sql.gz`
- `createdb vergeo5_restore_drill_*` on **local** Postgres 16
- `zcat … | sed strip \\restrict | psql` into isolated DB
- verification SQL (tables, migrations, RLS, counts)
- `dropdb` isolated DB afterwards

## Rollback

- **Not executed** against production (API digest unknown; tip mismatch; risk). Candidates recorded only.

## Load

- Offline: `python3 -m py_compile load/invariant-check.py`
- Offline: `node --check` on `load/k6/{browse,checkout}-load.js` (copied `.mjs`)
- Threshold encoding inspection via ripgrep — thresholds unchanged
- **Not executed:** `k6 run` (k6 absent; no approved staging target; API 502)

## Explicitly not run

- OCI Object Storage list / production restore
- Vercel production promote/rollback
- Real Lenco charges
- `public_launch` flip
