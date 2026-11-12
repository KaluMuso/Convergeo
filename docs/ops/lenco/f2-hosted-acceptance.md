# F2 isolated hosted acceptance

Status: executable source prepared; **NOT_RUN on PostgreSQL/PostgREST here**.
Session 3 reviews source; the coordinator alone integrates after target/deployment
guard checks. Recheck #716 reservations. No dispatch or shared application is
performed by this packet.

## Composition and preservation

Accepted base: `8f78448e4b340787fae98eeee58c372cc5ded307`, tree
`11593d708d8011a346ea24048a7b2b09476a44d5`. Apply updated full F1 once
(122832 bytes; SHA-256 `310faa3093d9c02c00bc19ba87e686d18140297d5defa6d007b141157e67299e`,
checkpoint 5887753414), then the delivered F2-only cumulative patch once. Do not
also apply the old embedded dependency or small F1 delta. Verify the resulting
tree against the handoff. Preserve source, migration checksums and logs first.
F1's actual FAILED observation now reaches F2; no second normalizer was added.
Controlled HTTP is synthetic and does not prove provider sandbox acceptance.

## Reuse the accepted stack

Use the existing qualified isolated GitHub Actions service job: Node22, frozen
pnpm/uv locks, PostgreSQL17 `pgvector/pgvector:0.8.0-pg17-trixie`, PostgREST
`public.ecr.aws/supabase/postgrest:v14.14`, unchanged
`scripts/ci/critical_real_stack_http.py` gateway/preflight. Run the unchanged
`scripts/ci/run-critical-real-stack.sh` 88-case gate separately on this tree;
its prior pass is not inherited. Do not rebuild its infrastructure.

The supplemental runner accepts **pre-provisioned disposable state**. Reuse the
accepted job's Auth/role/probe bootstrap and start/stop functions in a separate
isolated job lifecycle, so the 88 gate's cleanup does not conflict. Create from
`template0`; never clone shared data or target an owner workstation/server.

| Phase    | Database                 | Probe group  | Schema                                                           |
| -------- | ------------------------ | ------------ | ---------------------------------------------------------------- |
| pristine | `ci_critical_collection` | `collection` | Complete current migration replay                                |
| upgrade  | `ci_critical_prepaid`    | `prepaid`    | Accepted baseline, seed evidence, then four allocated migrations |

Each database needs the accepted standard local Auth columns,
`tests/lane_d/local_postgrest_auth_shim.sql`, and a matching row in
`ci_critical_binding_probe(group_name,database_name)`. Revoke probe access from
PUBLIC/anon/authenticated; grant service_role SELECT. PostgREST connects as
`ci_critical_authenticator`, NOSUPERUSER/NOBYPASSRLS/NOINHERIT, granted
anon/authenticated/service_role. Retain real role attributes/membership output.
Browser denial tests use actual JWT-scoped PostgREST. The unchanged preflight
checks SQL/HTTP identity and invalid JWT/anon denial.

Required environment **names only**: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`,
`PGDATABASE`, `SUPABASE_DB_URL`, `SUPABASE_URL`, `SUPABASE_REST_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `LANE_D_POSTGREST_URL`,
`LANE_D_JWT_SECRET`, `LANE_D_WEBHOOK_TOKEN`, `F2_POSTGREST_CONTAINER`, `RUNNER_TEMP`.
Use disposable test JWTs and loopback bindings. Suppress credential/DSN/header
output; preserve sanitized logs only. Never load Lenco credentials here.

## Exact phase commands

Run from the composed repository root. Set PGDATABASE/SUPABASE_DB_URL to the
phase's dedicated database without printing values. Creation/start/stop belongs
to the coordinator's reviewed isolated bootstrap, not this lane.

Pristine:

```sh
bash scripts/ci/migration-replay.sh > "$RUNNER_TEMP/f2-pristine-migrations.log" 2>&1
# Apply accepted Auth/probe bootstrap and start qualified HTTP against collection.
bash scripts/drills/run-f2-real-stack.sh pristine
```

Upgrade: use an additional baseline worktree only to replay its unchanged schema,
not to reconstruct F2. Apply the accepted Auth/probe bootstrap for prepaid before
the fixture seed; start qualified HTTP for this database.

```sh
git worktree add --detach "$RUNNER_TEMP/f2-accepted-baseline" 8f78448e4b340787fae98eeee58c372cc5ded307
bash "$RUNNER_TEMP/f2-accepted-baseline/scripts/ci/migration-replay.sh" > "$RUNNER_TEMP/f2-upgrade-baseline.log" 2>&1
# Accepted Auth/probe bootstrap and HTTP binding for ci_critical_prepaid.
(
  cd services/api
  PYTHONPATH=. uv run --no-sync python ../../scripts/drills/f2_upgrade_probe.py seed "$RUNNER_TEMP/f2-upgrade-before.json"
)
for migration in \
  20260929120000_service_payment_obligations_and_claims.sql \
  20260929120001_service_collection_settlement.sql \
  20260929120002_funded_service_completion.sql \
  20260929120003_adopt_existing_service_obligations.sql; do
  psql -X -v ON_ERROR_STOP=1 -f "supabase/migrations/$migration" > "$RUNNER_TEMP/$migration.log" 2>&1
done
psql -X -v ON_ERROR_STOP=1 -c "NOTIFY pgrst, 'reload schema';" >/dev/null
# Wait for PostgREST schema reload before new RPC invocation.
(
  cd services/api
  PYTHONPATH=. uv run --no-sync python ../../scripts/drills/f2_upgrade_probe.py verify "$RUNNER_TEMP/f2-upgrade-before.json"
)
bash scripts/drills/run-f2-real-stack.sh upgrade
```

The upgrade probe seeds pending, existing receipt, legacy card receipt and
ambiguous rows **before** F2 schema exists. It invokes actual baseline settlement
for labelled synthetic evidence, compares payment/receipt/ledger/postings and
checks no canonical proof is fabricated. It supplements the 35 cases; it is not
provider acceptance. Post-migration cases repeat adoption and ambiguity holds.

Run sequentially without pytest-xdist. The required manifest retains all original
13 identities plus 22 new expanded identities. Independent connections and unique
barrier triggers force opposing schedules. Each phase requires **35 executed,
35 pass, zero failed/skipped/xfailed/missing/duplicate/unexpected identities**.
The supplemental reporter rejects skipped JUnit even when pytest exits zero; it
does not replace the accepted 88 reporter. Related service/order suites run after
F2; their JUnit is also machine-checked. Empty, missing, duplicate, failed or
skipped related execution rejects the combined result, even if pytest exits zero.

Run F1's two no-skip real-stack identities in separate declared disposable state
per checkpoint 5887753414. Preserve F2's integrated FAILED-poller cases in both
phases; do not share fixtures concurrently.

## Remaining gates

After reviewed migrations execute, run the existing qualified `scripts/gen-types.sh`
with the accepted public/GraphQL schema configuration. Retain generated diff and
repeat for determinism. Never hand-edit db.ts. Run shared-types and affected
Customer/Vendor/Admin package typecheck/build/test scripts under frozen locks.
Keep accepted typegen/security workflows unchanged.

Admin passed this continuation under Node22/frozen locks; no base comparison or
font repair was needed. Real schema/type generation, pristine/upgrade replay,
PL/pgSQL invocation, roles, concurrency/rollback, combined 88 and provider-backed
acceptance remain **NOT_RUN locally**. The expanded local API run retains the
existing F1 internal-poll-route fixture failure separately; focused passes do not
waive it.

Source review, hosted CI, shared migration, sandbox transaction and launch remain
separate approvals. Policy is DRAFT / NOT EFFECTIVE; `f2-policy-to-test.md` maps
FP/Q decisions. No fixture percentage, commission or timer becomes a live rule.
This packet does not certify provider-backed products/services/events. Use the
canonical sandbox-money drill only after its separate authorization.
