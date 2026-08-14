# Staging sandbox ledger repair plan (DO NOT EXECUTE from CI)

This document describes the **one-time, human-operated** ledger normalization for
`vergeo-sandbox` (`iyasmrmbcrvlfxpzescb`) after the equivalence evidence in
`scripts/ci/staging-migration-equivalence.json` has been reviewed and approved.

## Safety boundary

- Target project ref: `iyasmrmbcrvlfxpzescb` only
- **Forbidden:** `dpadrlxukcjbewpqympu` (production)
- No schema DDL in this procedure — ledger metadata only
- Run only from an operator workstation with staging credentials
- Capture before/after ledger artifacts and stop on any unexpected row

## Pre-repair evidence (verified 2026-08-13)

| Field                | Value                                                              |
| -------------------- | ------------------------------------------------------------------ |
| Repository SHA       | `9922486d8fa0ed5443a150a5c236fb64f1200791`                         |
| Ledger row count     | 103                                                                |
| Ledger digest        | `3332cd5481de7c1040cd60e3f44d7aec02c8d17714d99a51e13f6ea0cc22b1bd` |
| Equivalence manifest | `scripts/ci/staging-migration-equivalence.json`                    |

## Expected pre-repair noncanonical rows

| Remote version   | Disposition                                             |
| ---------------- | ------------------------------------------------------- |
| `20260813071956` | Exact alias → `0096`                                    |
| `20260813072721` | Exact alias → `20260809214010`                          |
| `20260813072742` | Exact alias → `20260812010000`                          |
| `20260813073039` | Exact alias → `20260813063754`                          |
| `20260813072110` | Superseded rehearsal — retain schema, revert ledger row |
| `20260813072511` | Superseded rehearsal — retain schema, revert ledger row |
| `20260813072919` | Superseded rehearsal — retain schema, revert ledger row |

## Ordered repair procedure (Supabase CLI)

Run from repository root after `supabase link --project-ref iyasmrmbcrvlfxpzescb`.

### 1. Capture before ledger

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version || ':' || name FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-before.txt
```

### 2. Revert noncanonical ledger rows (no DDL)

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

### 3. Mark canonical versions as applied (schema already present)

```bash
supabase migration repair --status applied 0096
supabase migration repair --status applied 20260809214010
supabase migration repair --status applied 20260812010000
supabase migration repair --status applied 20260813063754
```

### 4. Capture after ledger and verify

Expected applied prefix (100 rows):

- `0001` … `0095`
- `0096`
- `20260802153539`
- `20260809214010`
- `20260812010000`
- `20260813063754`

Expected **pending** repository migrations (applied later via normal `db push`):

1. `20260812090000` — product strategy integrity constraints
2. `20260813064106` — product strategy core contract
3. `20260813150000` — `public.approve_kyc_vendor(...)` (verify absent before apply)

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-after.txt

python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "$(git rev-parse HEAD)" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-after.txt \
  --ledger-source live-query
```

Preflight must report `"ledger_repair_required": false` and list the three pending
versions above.

### 5. Apply truly pending schema (separate authorized window)

Only after steps 1–4 succeed:

```bash
supabase db push --include-all
bash scripts/ci/reconcile-staging-migrations.sh
```

## Post-repair verification checklist

- [ ] `public.approve_kyc_vendor(...)` absent before step 5; present only after `20260813150000`
- [ ] Rehearsal schema retained: `private.rate_counter_scope_manifest`, 6-arg `record_listing_view`, `private.has_role`
- [ ] Production project ref never linked
- [ ] Before/after ledger artifacts archived with operator + timestamp

## Rollback

Ledger repair is metadata-only. If a repair step fails mid-flight, capture the
ledger, do **not** run `db push`, and restore ledger rows using the inverse
`supabase migration repair` operations documented above against the before artifact.
