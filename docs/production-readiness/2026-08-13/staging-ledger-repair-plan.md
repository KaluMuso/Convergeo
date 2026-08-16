# Staging sandbox ledger repair plan (DO NOT EXECUTE from CI)

> **EXECUTED — STG-LEDGER-02 (2026-08-16 UTC).** Staging `iyasmrmbcrvlfxpzescb` ledger
> normalized and **eight** canonical migrations applied through tip `20260815230000`.
> Evidence: `docs/production-readiness/2026-08-16/stg-ledger-02/EXECUTION-REPORT.md`.
> The procedure below is retained as historical operator documentation.

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
verify live sandbox ledger + physical state
→ revert the seven noncanonical ledger rows
→ mark ONLY the four exact aliases applied:
     0096, 20260809214010, 20260812010000, 20260813063754
→ leave **eight** canonical migrations pending (see repository test contract):
     20260812090000, 20260813064106, 20260813150000,
     20260813160000, 20260813160100, 20260813160200,
     20260815194500, 20260815230000
→ run convergence preflight:
     ledger drift = clean
     unresolved physical drift = zero
     known pending migration drift = allowed
     schema_apply_required = true
→ normal supabase db push applies all eight
→ exact ledger reconciliation
→ extract physical state again
→ require final canonical physical parity = PASS
```

**Do not** mark `20260813160000`, `20260813160100`, or `20260813160200` as applied
during ledger repair. Those migrations are **not** physically identical to the
rehearsal state (for example live `record_listing_view` lacks
`p_surface text DEFAULT 'unknown'`). They must execute through the normal migration
mechanism.

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

| Remote version   | Disposition                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------------- |
| `20260813071956` | Exact alias → `0096` (mark applied after revert)                                              |
| `20260813072721` | Exact alias → `20260809214010`                                                                |
| `20260813072742` | Exact alias → `20260812010000`                                                                |
| `20260813073039` | Exact alias → `20260813063754`                                                                |
| `20260813072110` | Superseded rehearsal → revert only; canonical via `20260813160000` + `20260813160100` db push |
| `20260813072511` | Superseded rehearsal → revert only; canonical via `20260813160200` db push                    |
| `20260813072919` | Superseded rehearsal → revert only; canonical via `20260813160100` db push                    |

## Step 1 — Capture before ledger and physical state

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version || ':' || name FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-before.txt

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA \
  -f scripts/ci/extract-physical-schema-state.sql \
  | tee /tmp/sandbox-physical-before.json
```

## Step 2 — Verify drift against repository HEAD

```bash
export EXPECTED_SOURCE_SHA="$(git rev-parse HEAD)"
python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "${EXPECTED_SOURCE_SHA}" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-before.txt \
  --physical-state-file /tmp/sandbox-physical-before.json \
  --ledger-source live-query
```

Expect `"ledger_repair_required": true`. Live sandbox physical state **must fail**
`record_listing_view_defaults` until `20260813160100` executes via db push.

## Step 3 — Prove fresh-replay physical parity (no Production)

On a disposable database, apply **repository migrations only** through HEAD, extract
physical state, and compare to `staging-physical-parity-manifest.json`. The checked-in
fixture `scripts/ci/fixtures/repository-replay-physical-state-pre-parity-20260814.json`
documents the pre-parity replay baseline for regression tests.

Rehearsal-state replay: apply the three canonical migrations
(`20260813160000`–`20260813160200`) on a fixture matching live rehearsal physical
state; final schema must equal fresh canonical replay
(`scripts/ci/fixtures/sandbox-physical-state-post-canonical-push-20260814.json`).

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

## Step 5 — Mark ONLY exact alias versions as applied (schema already present)

```bash
supabase migration repair --status applied 0096
supabase migration repair --status applied 20260809214010
supabase migration repair --status applied 20260812010000
supabase migration repair --status applied 20260813063754
```

**Do not** mark `20260813160000`, `20260813160100`, or `20260813160200` applied here.

## Step 6 — Capture after ledger and verify preflight (pre-db-push)

Expected applied prefix (100 rows): `0001` … `0096`, `20260802153539`,
`20260809214010`, `20260812010000`, `20260813063754`.

Expected **pending** repository migrations (applied later via normal `db push`):

1. `20260812090000` — product strategy integrity constraints
2. `20260813064106` — product strategy core contract
3. `20260813150000` — `public.approve_kyc_vendor(...)` (verify absent before apply)
4. `20260813160000` — rate counter scope manifest (re-entrant on rehearsal schema)
5. `20260813160100` — listing view surface telemetry (`p_surface DEFAULT 'unknown'`)
6. `20260813160200` — security definer hardening (guarded extension relocation)
7. `20260815194500` — privileged function EXECUTE hardening (SEC-DB-01)
8. `20260815230000` — refund provider-authoritative active index

```bash
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version" \
  | tee /tmp/sandbox-ledger-after-repair.txt

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA \
  -f scripts/ci/extract-physical-schema-state.sql \
  | tee /tmp/sandbox-physical-after-repair.json

export EXPECTED_SOURCE_SHA="$(git rev-parse HEAD)"
python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "${EXPECTED_SOURCE_SHA}" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-after-repair.txt \
  --physical-state-file /tmp/sandbox-physical-after-repair.json \
  --ledger-source live-query
```

Preflight must report:

- `"ledger_repair_required": false`
- `"unresolved_physical_drift": []`
- `"pending_migration_physical_drift"` may include `record_listing_view_defaults`
- `"schema_apply_required": true`
- `"truly_pending_repository_migrations"` lists all six migrations above

## Step 7 — Apply truly pending schema (separate authorized window)

Only after steps 1–6 succeed:

```bash
supabase db push --include-all
bash scripts/ci/reconcile-staging-migrations.sh
```

## Step 8 — Post-push reconciliation

```bash
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA \
  -f scripts/ci/extract-physical-schema-state.sql \
  | tee /tmp/sandbox-physical-after-push.json

export EXPECTED_SOURCE_SHA="$(git rev-parse HEAD)"
python3 scripts/ci/schema_convergence.py \
  --staging-preflight \
  --json-plan \
  --expected-source-sha "${EXPECTED_SOURCE_SHA}" \
  --target-kind sandbox \
  --target-project-ref iyasmrmbcrvlfxpzescb \
  --ledger-file /tmp/sandbox-ledger-after-push.txt \
  --physical-state-file /tmp/sandbox-physical-after-push.json \
  --ledger-source live-query
```

Post-push preflight must report zero `unresolved_physical_drift`, zero
`pending_migration_physical_drift`, and `"schema_apply_required": false`.

## Post-repair verification checklist

- [ ] `public.approve_kyc_vendor(...)` absent before step 7; present only after `20260813150000`
- [ ] Rehearsal schema retained through ledger repair; canonical migrations applied only via db push
- [ ] `record_listing_view` proves `p_surface DEFAULT 'unknown'` after `20260813160100`
- [ ] Legacy 4-arg RPC call succeeds after `20260813160100` (PostgREST/PostgreSQL defaults)
- [ ] Physical parity manifest passes against post-push extractor output
- [ ] Production project ref never linked
- [ ] Before/after ledger + physical artifacts archived with operator + timestamp

## Rollback

Ledger repair is metadata-only. If a repair step fails mid-flight, capture the
ledger, do **not** run `db push`, and restore ledger rows using the inverse
`supabase migration repair` operations documented above against the before artifact.

## Master-as-production release order (RELCTRL-01)

Do **not** merge STG-DRIFT-02 into `master` until staging certification completes at
the exact PR-head candidate SHA. After final code review and terminal CI/Performance:

1. Freeze final PR-head SHA
2. Prove current `master` has not moved unexpectedly
3. Advance `staging` to the exact PR-head candidate (not `master`)
4. Expect first `deploy-staging` attempt to fail closed at ledger repair
5. Execute the separately authorized one-time sandbox ledger repair (steps 1–6)
6. Rerun `deploy-staging` so the six pending migrations execute normally
7. Prove schema/RLS/typegen/API/three-portal Preview/E2E at the exact candidate SHA
8. Create merge-release evidence for that exact SHA
9. Only then merge into `master`

Steps 3–9 are human-operated; this document does not authorize executing them from CI.

## Sandbox-only physical cleanup (not required for current rehearsals)

All three superseded rehearsals are **CANONICALIZE** decisions in STG-DRIFT-02.
No sandbox-only DDL cleanup is required when canonical migrations land in the
repository and pass physical parity after db push.
