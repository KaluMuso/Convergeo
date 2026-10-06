# Service adoption upgrade guard

This is a local implementation for independent review under the continuity
handbook's R2 gate. It does not authorize a shared migration or certify R3–R6.

Immutable `20260929120003_adopt_existing_service_obligations.sql` adopts legacy
service orders before the later ambiguity-hold repair. Two otherwise eligible
orders for different jobs/vendors can share a deposit checkout. The second
deposit obligation then hits the unique checkout constraint and prevents the
upgrade from reaching the later repair. An empty database replay cannot detect
this failure.

`scripts/ci/apply_service_adoption.py` executes the original adoption bytes in
one PostgreSQL transaction. Inside that transaction only, it adds shared-checkout,
foreign-obligation and existing-balance guards to the original obligation
routine. Ambiguous orders receive the existing durable adoption-hold action;
no money, receipt, payment, order status or foreign checkout is changed. Healthy
orders retain the original adoption logic. The original routine, grants and
signature are restored before commit. SQL errors roll back both adoption and
temporary DDL; unique violations are never swallowed.

The helper verifies SHA256 of both immutable input migrations and verifies that
the installed function body and execution metadata match the reviewed authority
before replacing it. Security mode, volatility, parallel/strict/leakproof flags,
empty search path and client/service grants must match; identical routine bodies
with changed execution privileges are rejected. Owner identity is preserved
without assuming the hosted role name.
It fails rather than overwriting newer financial authority. Routine replacement
is transaction-local to the applying session and is restored before other
sessions can observe a committed change.

The repository migration replay and accepted-baseline financial upgrade runner
call this helper at the `120003` boundary. The local composition includes the
preserved financial/F3 changes and merchant `170100`: 127 accepted baseline
migrations plus eight explicit additions, 135 total. All 131 SQL files on the
published `00863c24` candidate remain byte-identical.

The upgrade probe seeds healthy, pending, received, card, invalid-snapshot,
shared-checkout and foreign-balance cases before the F2 migrations. It verifies
the complete ordered upgrade and preservation of existing order/item/checkout
and monetary records, with exactly one hold per ambiguous order. This extends
upgrade fixtures without removing any of the 804 mandatory test identities.

## Shared deployment boundary

`supabase db push` does **not** invoke this repository helper. Do not treat a
passing CI/local replay as proof that a direct hosted CLI upgrade is safe.
The release operator must review and provide an explicit migration-ledger-aware
application plan for this boundary before R4 application. In particular, do not
run the helper and then blindly replay the raw `120003` file a second time.
No shared ledger update or hosted deployment path is installed by this change.

Preview the exact transaction without connecting to a database:

```sh
python3 scripts/ci/apply_service_adoption.py --render
```

Execute only on an approved bound database using the established `PG*`
configuration. The installer uses `psql -X --single-transaction` and
`ON_ERROR_STOP=1`. Do not record credentials in reports.

The newer five-path coordinator patch identified by SHA256
`96509bebfa39233b7b4ea17fa885ae0cda78dffe9cc4665f8ceb903ae65c3e75`
was absent from the supplied packet. Its actual bytes and independent review
remain required. The older nine-path workflow draft has not been installed as
a substitute. Dedicated hosted F3 wiring, qualified 135-input generated types,
independent financial/merchant review, and hosted candidate acceptance remain
separate requirements.

## Read-only shared push prerequisite

The staging push now runs `scripts/ci/guard_shared_service_adoption.py` immediately
before `supabase db push --include-all`, binding both operations to the same
explicit `SUPABASE_DB_URL`. It refuses pending `120003`, missing/null/aliased or
changed history, and absent review evidence. The canonical installed row must
contain the exact original filename name, version and one original SQL input in
`statements`; null history or guessed segmentation is not accepted. No SQL
migration is executed and no migration ledger is repaired by this prerequisite.
Production's existing workflow has no database push and remains unchanged.

The protected staging variable `STAGING_SERVICE_ADOPTION_REVIEW_EVIDENCE_JSON`
must supply a real application/review record with these fields: `purpose`
(`SHARED_ADOPTION_APPLICATION_REVIEW`), current `source_sha`, `project_ref`,
`adoption_sha256`, `canonical_row_sha256` (SHA256 of sorted-key compact JSON of
that exact ledger row), `review_verdict` (`APPROVED_FOR_TARGET_APPLICATION`),
named `reviewer`, `review_record_sha256`, and HTTPS `application_record_url` /
`review_record_url`. These are supplied attestations, not inferred or generated
approval: the guard checks their binding and referenced basis, not an external
reviewer's identity or signature. Release reviewers must inspect those real
records and approve the target independently; do not populate the variable with
synthetic rehearsal evidence. Missing target application evidence keeps shared
push blocked even after local rehearsals pass. Administrative concurrent ledger
changes still require the operator's stopped/drained migration window; this
read-only prerequisite does not install a shared transaction or authorize it.

The shared prerequisite additionally restricts the DSN to the established staging
project's standard direct hostname or session-pooler hostname/`postgres.<ref>`
username, database `postgres`, and native port 5432. Production, custom/loopback
hosts and connection-routing query parameters are rejected. `PGHOSTADDR`,
`PGSERVICE`, `PGSERVICEFILE` and `PGOPTIONS` are cleared for the read-only query so
libpq environment indirection cannot redirect its target. The local SQL control
uses the same read-only query and pure validator on an explicitly owned fixture;
it does not relax this shared endpoint restriction or manufacture release proof.
