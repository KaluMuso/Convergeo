# Schema convergence control — 2026-08-13

## Purpose and current boundary

This is the executable evidence contract for reconciling repository history,
the isolated sandbox, and production. It does **not** apply a migration and it
does not make a production database a CI target.

The repository checker is `scripts/ci/schema_convergence.py`; the only adapter
that reads a remote ledger is `scripts/ci/rehearse-schema-convergence.sh`. The
adapter accepts only the documented sandbox project ref, performs one
read-only `schema_migrations` query, and fails if that query did not yield a
ledger. It never invokes `supabase db push`.

## Cohorts and v1 scope lock

The checked-in [cohort manifest](../../../scripts/ci/schema-convergence-cohorts.json)
is the machine-readable source of truth. Its cohorts are:

| Cohort | Sandbox rehearsal tip | Required evidence |
| --- | --- | --- |
| `dark-ship-foundation` | `0079` | ledger, flags false, RLS matrix, advisor review |
| `location-social-foundation` | `0084` | ledger, location-stock smoke, enquiry RLS, licence fail-closed check |
| `future-compatible-schema` | `20260812010000` | ledger, generated types, real-role RLS, v1 release-profile smoke, advisors |
| `v1-activation-hold` | no automated execution | dated ADR, API enforcement PR, RLS grant review, release-profile regression |

`D33` and `D34` remain release constraints even when future-compatible schema
exists: v1 accepts only product class `A`, `new`/`refurbished`, sale unit
`each`, stocked fulfilment, and the single `admin` role. `0085`, `0087`,
`0091`, and `0095` are **schema compatibility**, not permission to expose
per-measure, made-to-order, used, RFQ, `superadmin`, or `moderator` behaviour.
The checker refuses any altered release profile. A follow-up API/RLS pebble
must make the same profile enforceable at every write and discovery boundary
before the `v1-activation-hold` may be removed.

## Sandbox rehearsal command

This command is read-only; it verifies a completed rehearsal, it does not run
one. Values are secret references in the environment and must never be copied
into an issue, PR, or evidence file.

```bash
SCHEMA_TARGET_KIND=sandbox \
SCHEMA_TARGET_PROJECT_REF=iyasmrmbcrvlfxpzescb \
SCHEMA_COHORT=future-compatible-schema \
SUPABASE_DB_URL="$SUPABASE_DB_URL" \
bash scripts/ci/rehearse-schema-convergence.sh
```

Save the checker output, its `manifest_sha256`, the immutable source SHA, and
the exact cohort id as a GitHub Actions artifact. A missing, empty, reordered,
unknown, or non-contiguous ledger is a failure, not a warning.

## Manual production change-window checklist

Production migration activity is a founder-approved, human-operated window;
it is never CI and it is never inferred from a sandbox pass.

1. Name the release SHA, operator, reviewer, cohort, planned window, and an
   application rollback SHA. Confirm no open PR changes the selected migration
   chain.
2. Read the production ledger and archive the redacted result. Compare it to
   the repository manifest; stop on any unknown, reordered, duplicate, or
   non-contiguous entry.
3. Create and independently verify a restorable production backup/PITR point.
   Record only backup identifiers, timestamps, checksums, and ledger tip.
4. Repeat the exact cohort in the isolated sandbox at the selected SHA. Archive
   migration replay, generated-type diff, real-role RLS matrix, relevant smoke
   evidence, security/performance advisors, and the release-profile proof.
5. Reconcile advisor findings using the function inventory. Do not resolve a
   linter warning through a blanket `REVOKE` or by making an internal function
   publicly callable.
6. During the window, a human operator reviews the dry-run plan and applies
   only the approved additive cohort. No feature flag changes, credential
   changes, payments, WAHA, or Clips activation belong to this action.
7. Re-read the production ledger; regenerate committed types from the applied
   schema; run real-role RLS, API health/readiness/fingerprint, cart, search,
   CORS, and customer/vendor/admin smoke checks.
8. Monitor errors and database metrics for the agreed observation period. If
   application compatibility fails, roll back app images/frontends and retain
   the additive schema. Restore the database only for a confirmed migration
   corruption incident under the disaster-recovery runbook.
9. Attach the evidence pack to the release decision and update release gates.
   A missing artifact is a `NO_GO`.

## Explicit non-gates

- A green migration replay is not a production ledger proof.
- A GitHub Actions success is not authority to run `supabase db push` on
  production.
- The presence of future columns, functions, or role values is not feature
  activation.
- `public_launch`, payments, Clips, and `waha_vendor_intake` remain unchanged
  by this control.
