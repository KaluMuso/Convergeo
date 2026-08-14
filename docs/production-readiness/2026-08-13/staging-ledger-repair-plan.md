# Staging sandbox ledger repair plan (DO NOT EXECUTE from CI)

This document describes the **one-time, human-operated** ledger normalization for
`vergeo-sandbox` (`iyasmrmbcrvlfxpzescb`) after equivalence and physical parity
evidence in `scripts/ci/staging-migration-equivalence.json` and
`scripts/ci/staging-physical-parity-manifest.json` have been reviewed and approved.

## Safety boundary

- Target project ref: `iyasmrmbcrvlfxpzescb` only
- **Forbidden:** `dpadrlxukcjbewpqympu` (production)
- No schema DDL in the ledger repair procedure itself — ledger metadata only
- Run only from an operator workstation with staging credentials
- Capture before/after ledger and physical-state artifacts; stop on any unexpected row

## Ordered procedure (must follow this sequence)

```text
verify exact live ledger
→ verify exact physical drift (extract-physical-schema-state.sql + preflight)
→ canonicalize desired rehearsal effects in repository
   OR separately clean unwanted sandbox-only effects
→ prove fresh-replay physical parity (repository migrations only)
→ only then perform migration ledger repair
→ re-run schema-convergence preflight (ledger + physical)
→ only then allow normal db push
```

**Do not** remove rehearsal ledger rows while unrepresented physical schema remains.
Ledger normalization alone must not clear `staging_only_retained_schema` drift.

## Pre-repair evidence (verified 2026-08-13, ledger unchanged 2026-08-14)

| Field                | Value                                                               |
| -------------------- | ------------------------------------------------------------------- |
| Repository SHA       | `194f35afe42fe22f6b386e4d69b5872eec045ce2` (master at STG-DRIFT-02) |
| Ledger row count     | 103                                                                 |
| Ledger digest        | `3332cd5481de7c1040cd60e3f44d7aec02c8d17714d99a51e13f6ea0cc22b1bd`  |
| Equivalence manifest | `scripts/ci/staging-migration-equivalence.json`                     |
| Physical manifest    | `scripts/ci/staging-physical-parity-manifest.json`                  |

## Expected pre-repair noncanonical rows

| Remote version   | Disposition                                                         |
| ---------------- | ------------------------------------------------------------------- |
| `20260813071956` | Exact alias → `0096`                                                |
| `20260813072721` | Exact alias → `20260809214010`                                      |
| `20260813072742` | Exact alias → `20260812010000`                                      |
| `20260813073039` | Exact alias → `20260813063754`                                      |
| `20260813072110` | Superseded rehearsal → canonical `20260813160000`, `20260813160100` |
| `20260813072511` | Superseded rehearsal → canonical `20260813160200`                   |
| `20260813072919` | Superseded rehearsal → canonical `20260813160100`                   |

## Step 1 — Capture before ledger and physical state

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version || ':' || name FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-before.txt

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA \
  -f scripts/ci/extract-physical-schema-state.sql \
  | tee /tmp/sandbox-physical-before.json
```

## Step 2 — Verify physical drift against repository HEAD

```bash
python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "$(git rev-parse HEAD)" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-before.txt \
  --physical-state-file /tmp/sandbox-physical-before.json \
  --ledger-source live-query
```

Expect `"ledger_repair_required": true` and `"schema_repair_required": true` on
pre-canonical master. After STG-DRIFT-02 merges, live sandbox physical state must
pass while ledger repair is still required.

## Step 3 — Prove fresh-replay physical parity (no Production)

On a disposable database, apply **repository migrations only** through HEAD, extract
physical state, and compare to `staging-physical-parity-manifest.json`. The checked-in
fixture `scripts/ci/fixtures/repository-replay-physical-state-pre-parity-20260814.json`
documents the pre-parity replay baseline for regression tests.

## Step 4 — Revert noncanonical ledger rows (no DDL)

Run from repository root after `supabase link --project-ref iyasmrmbcrvlfxpzescb`.

```bash
supabase migration repair --status reverted 20260813071956
supabase migration repair --status reverted 20260813072110
supabase migration repair --status reverted 20260813072511
supabase migration repair --status reverted 20260813072721
supabase migration repair --status reverted 20260813072742
supabase migration repair --status reverted 20260813072919
supabase migration repair --status reverted 20260813073039
```

Stop if any command reports an unexpected state.

## Step 5 — Mark canonical versions as applied (schema already present)

```bash
supabase migration repair --status applied 0096
supabase migration repair --status applied 20260809214010
supabase migration repair --status applied 20260812010000
supabase migration repair --status applied 20260813063754
supabase migration repair --status applied 20260813160000
supabase migration repair --status applied 20260813160100
supabase migration repair --status applied 20260813160200
```

## Step 6 — Capture after ledger and verify preflight

Expected applied prefix (103 rows): `0001` … `0096`, `20260802153539`,
`20260809214010`, `20260812010000`, `20260813063754`, `20260813160000`,
`20260813160100`, `20260813160200`.

Expected **pending** repository migrations (applied later via normal `db push`):

1. `20260812090000` — product strategy integrity constraints
2. `20260813064106` — product strategy core contract
3. `20260813150000` — `public.approve_kyc_vendor(...)` (verify absent before apply)

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-after.txt

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA \
  -f scripts/ci/extract-physical-schema-state.sql \
  | tee /tmp/sandbox-physical-after.json

python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "$(git rev-parse HEAD)" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-after.txt \
  --physical-state-file /tmp/sandbox-physical-after.json \
  --ledger-source live-query
```

Preflight must report `"ledger_repair_required": false`, `"schema_repair_required": false`,
and list the three pending product-strategy/KYC migrations above.

## Step 7 — Apply truly pending schema (separate authorized window)

Only after steps 1–6 succeed:

```bash
supabase db push --include-all
bash scripts/ci/reconcile-staging-migrations.sh
```

## Post-repair verification checklist

- [ ] `public.approve_kyc_vendor(...)` absent before step 7; present only after `20260813150000`
- [ ] Rehearsal schema retained and manifest-green: `private.rate_counter_scope_manifest`, 6-arg `record_listing_view`, `private.has_role`
- [ ] Physical parity manifest passes against live extractor output
- [ ] Production project ref never linked
- [ ] Before/after ledger + physical artifacts archived with operator + timestamp

## Rollback

Ledger repair is metadata-only. If a repair step fails mid-flight, capture the
ledger, do **not** run `db push`, and restore ledger rows using the inverse
`supabase migration repair` operations documented above against the before artifact.

## Sandbox-only physical cleanup (not required for current rehearsals)

All three superseded rehearsals are **CANONICALIZE** decisions in STG-DRIFT-02.
No sandbox-only DDL cleanup is required when canonical migrations land in the
repository and pass physical parity. If a future audit marks an effect
`REVERT_FROM_SANDBOX`, document a human-operated cleanup script here that:

- targets `iyasmrmbcrvlfxpzescb` only
- captures `pg_get_*` definitions before mutation
- fails on unexpected definitions
- never ships in the Production migration chain
