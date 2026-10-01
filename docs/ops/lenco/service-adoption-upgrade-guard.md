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
the installed function body matches the reviewed authority before replacing it.
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
