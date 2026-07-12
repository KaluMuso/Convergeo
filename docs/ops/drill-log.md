# Backup-restore drill log (M15-P09)

Append-only log of Vergeo5 restore drills. Each entry records the date, operator,
target, timings, and the pass/fail of `scripts/ops/restore-staging.sh` (which restores a
dump into a **fresh** DB and asserts core tables + config seed + migration currency via
`scripts/ops/restore-smoke.sql`).

- **RTO target:** ≤ 30 min · **RPO target:** ≤ 24 h (see `docs/ops/runbook-disaster-recovery.md`).
- Nightly source dumps: `infra/scripts/db-dump.sh` → OCI `db/vergeo5-<ts>.sql.gz`.
- No secrets are ever pasted here — DB URLs are redacted / referenced by env var name.

---

## Drill entry template (copy for each drill)

```
### <YYYY-MM-DD> — <local | staging> restore drill — <PASS | FAIL>
- Operator:        <name>
- Source:          <staging nightly dump object | freshly dumped $SOURCE_DB_URL (redacted)>
- Target:          <$SUPABASE_DB_URL restore DB (redacted)>
- Migrations repo: <N> files, latest <NNNN>
- Timings:         dump <Xs> · restore <Ys> · smoke <Zs> · TOTAL <Ts>
- Smoke result:    core tables OK / seed non-empty OK / migrations current <NNNN>==<NNNN>
- Notes / anomalies: <...>
```

---

## 2026-07-12 — LOCAL restore drill — PASS

Executed by the M15-P09 implementation in this build environment. **No live staging DB is
reachable here**, so this is a full end-to-end drill against an ephemeral local Postgres 16
cluster (with pgvector) that stands in for the staging DB. It exercises the exact
`restore-staging.sh` code path — dump → drop/create fresh target → `pg_restore` → smoke —
that the founder will run against real staging (§ founder-gated below).

### Environment set-up (local stand-in for staging)

```bash
# Ephemeral Postgres 16 cluster (client + server present; run as the 'postgres' user).
initdb -D /tmp/pgdata-m15p09 -U postgres --auth=trust
pg_ctl -D /tmp/pgdata-m15p09 -o '-p 5433 -k /tmp' start

# Build a staging-like SOURCE db: apply all migrations (via the existing replay helper)
# then record the Supabase migration ledger so the currency check has something to assert.
createdb -h /tmp -p 5433 -U postgres vergeo_src
PGHOST=/tmp PGPORT=5433 PGDATABASE=vergeo_src bash scripts/ci/migration-replay.sh
psql -h /tmp -p 5433 -U postgres -d vergeo_src <<'SQL'
CREATE SCHEMA IF NOT EXISTS supabase_migrations;
CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations
  (version text PRIMARY KEY, statements text[], name text);
-- one row per supabase/migrations/NNNN_*.sql (version = numeric prefix)
INSERT INTO supabase_migrations.schema_migrations (version, name)
SELECT split_part(f,'_',1), f FROM unnest(ARRAY[ /* 0001_… … 0029_analytics_unify.sql */ ]) AS f
ON CONFLICT DO NOTHING;
SQL
```

### 1. Dry-run (no DB touched)

```
$ bash scripts/ops/restore-staging.sh --dry-run
==> Vergeo5 restore drill
==> migrations dir:  <repo>/supabase/migrations (29 files, latest 0029)
==> smoke sql:       <repo>/scripts/ops/restore-smoke.sql
==> source:          $SOURCE_DB_URL (UNSET)
==> target:          $SUPABASE_DB_URL/$TARGET_DB_URL (UNSET)

Planned steps:
  1. pg_dump --format=custom --no-owner --no-privileges "$SOURCE_DB_URL" -f <tmp>/vergeo-restore-$ts.dump
  2. psql "<maintenance>" -c 'DROP DATABASE IF EXISTS <target>' -c 'CREATE DATABASE <target>'
  3. pg_restore --no-owner --no-privileges --exit-on-error -d "$TARGET_DB_URL" <tmp>/vergeo-restore-$ts.dump
  4. psql -v ON_ERROR_STOP=1 "$TARGET_DB_URL" -f <repo>/scripts/ops/restore-smoke.sql
  5. assert migration ledger count/latest == 29/0029

==> DRY RUN — no dump taken, no database created or modified.
# exit 0
```

### 2. Real local restore + smoke (fresh target)

```
$ SOURCE_DB_URL='postgresql://…@127.0.0.1:5433/vergeo_src' \
  SUPABASE_DB_URL='postgresql://…@127.0.0.1:5433/vergeo_restore' \
  bash scripts/ops/restore-staging.sh
==> dumping source -> /tmp/vergeo-restore-RbeLiP.dump
==> dump complete in 0s (420K)
==> recreating fresh target database 'vergeo_restore'
DROP DATABASE
CREATE DATABASE
==> restoring into 'vergeo_restore'
==> restore complete in 2s
==> running smoke invariants (<repo>/scripts/ops/restore-smoke.sql)
NOTICE:  SMOKE OK: 35 core tables present
NOTICE:  SMOKE OK: public.commission_rates has 9 row(s)
NOTICE:  SMOKE OK: public.delivery_zones has 3 row(s)
NOTICE:  SMOKE OK: public.platform_config has 16 row(s)
NOTICE:  SMOKE OK: public.feature_flags has 4 row(s)
NOTICE:  SMOKE OK: public.vendor_quotas has 3 row(s)
NOTICE:  SMOKE OK: public.prohibited_categories has 7 row(s)
NOTICE:  SMOKE OK: migration ledger has 29 rows, latest=0029
NOTICE:  SMOKE PASS: restore invariants hold
==> asserting migration ledger is current vs supabase/migrations/
==> ledger: 29 rows, latest 0029  |  repo: 29, 0029
==> migrations current: latest 0029 matches repo, ledger >= repo count
==> RESTORE DRILL PASSED — target 'vergeo_restore' restored and smoke-verified.

real    0m2.037s
# exit 0
```

### 3. Failure-path evidence (smoke fails loudly)

```
# Truncate a seed table, re-run smoke -> non-zero exit, loud failure:
$ psql "$SUPABASE_DB_URL" -c 'TRUNCATE platform_config;'
$ psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" -f scripts/ops/restore-smoke.sql
ERROR:  SMOKE FAIL: seed table public.platform_config is empty after restore   # exit 3

# Safety guards refuse dangerous targets:
$ SUPABASE_DB_URL='…/postgres'        bash scripts/ops/restore-staging.sh
ERROR: refusing to use 'postgres' as a restore target — point at a scratch DB   # exit 1
$ SOURCE_DB_URL=X SUPABASE_DB_URL=X   bash scripts/ops/restore-staging.sh
ERROR: SOURCE_DB_URL and target are identical — refusing to clobber the source  # exit 1
```

### Result

| Check                              | Result |
| ---------------------------------- | ------ |
| `bash -n restore-staging.sh`       | PASS   |
| `--dry-run`                        | PASS (exit 0, no mutation) |
| dump → fresh restore → smoke       | PASS (total ~2.0s local) |
| 35 core tables present             | PASS   |
| config seed tables non-empty       | PASS (9/3/16/4/3/7 rows) |
| migrations current (29 / 0029)     | PASS   |
| smoke fails on empty seed          | PASS (exit 3) |
| guards refuse prod / self-clobber  | PASS (exit 1) |

> Local timings (~2s) are **not** the RTO measurement — the ~420 KB local schema+seed is a
> fraction of real staging data. The ≤30-min RTO is measured in the founder-gated live drill.

---

## LIVE STAGING DRILL — founder-gated (deferred)

> **DEFERRED-AC.** Not runnable in the build environment: needs the real **staging Supabase
> DB** + a **nightly logical dump** + Vercel/OCI/Lenco context. Do **not** fake it. The
> founder (with staging access) runs this and pastes the transcript + wall-clock timing
> below. This closes the "live ≤30-minute staging restore" acceptance criterion.

**Pre-reqs:** `SUPABASE_DB_URL` = a **scratch staging restore** DB (never prod), a source
= staging DB URL or a nightly `.sql.gz`, `psql`/`pg_dump`/`pg_restore` 16 on PATH.

**Run (start a wall clock):**

```bash
date -u +'DRILL START %Y-%m-%dT%H:%M:%SZ'

# Option A — dump live staging (custom format) → fresh restore → smoke:
export SOURCE_DB_URL="$STAGING_DB_URL"           # staging (read)
export SUPABASE_DB_URL="$STAGING_RESTORE_DB_URL" # scratch restore target (dropped+recreated)
bash scripts/ops/restore-staging.sh

# Option B — restore the latest nightly gzip dump, then run the deep smoke:
cd infra && SUPABASE_DB_URL="$STAGING_RESTORE_DB_URL" bash scripts/db-restore.sh --latest && cd ..
psql -v ON_ERROR_STOP=1 "$STAGING_RESTORE_DB_URL" -f scripts/ops/restore-smoke.sql

date -u +'DRILL END %Y-%m-%dT%H:%M:%SZ'
```

**Record (paste into a new dated entry above):** START/END timestamps and **elapsed
minutes (must be ≤ 30)**; dump size; restore duration; smoke output (35 core tables, seed
non-empty, migrations current == latest repo migration); the source dump object name/age
(RPO must be ≤ 24 h); any anomalies. If elapsed > 30 min or any smoke assertion fails, open
a follow-up and note the remediation.
```
### <date> — staging restore drill — <PASS|FAIL>   <-- founder fills this in
```
