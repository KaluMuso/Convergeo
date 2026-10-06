# Clean staging rebuild proposal — decision only

Qualified source: draft PR 718 branch `codex/coordinator-ci-review-20261001`,
commit `6918e4530fabee6a4a6eea25c8e04cb4e88a34ca`, tree
`3207aa8a784539d7cc17448f999d6fbdb8be4876`, with 139 migration files.
Automatic CI run `37515050196` passed. Its original-body proof used the pinned
CLI's native three-column ledger; it did not prove preservation of the hosted
six-column history. A focused synthetic six-column suffix test is being prepared
locally and still needs independent review and automatic CI. This document authorizes no
database change. The qualified disposable profile uses PostgreSQL 17.6 and
vector 0.8.2 / pgcrypto 1.3 / pg_graphql 1.6.1. Hosted staging has PostgreSQL
17 with a different patch image and pg_trgm 1.6; local success does not prove
hosted parity. The bounded hosted survey described below is read-only evidence,
not a complete data or dynamic-SQL proof.

## Safest boundary

Keep current staging (`iyasmrmbcrvlfxpzescb`) intact. A **separate, isolated,
authorized, no-cost disposable staging candidate** with its own URL, secrets,
and Auth/Storage namespace is a conditional option; no such capacity has been
verified. Do not point any production, shared, or notification writer at it. If no isolated
no-cost target exists, stop: the Hetzner 4 GB host also runs production and n8n
and is not a disposable target. Do not reset, delete, or replace the existing
staging database as a shortcut.

The candidate starts empty and receives the 139 source migrations exactly
once in order. Preserve the old staging plane as the rollback reference until
separate cutover approval. This is a clean synthetic rebuild: transactional,
mock account, and rate-counter rows are **not imported**. Anyone needing stable
Auth IDs or historical mock transactions must request a different, scoped
preservation plan before execution.

| Surface in current staging                             | Candidate action and boundary                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 124 `public` tables and 1 private table                | Recreate structure from pinned migrations; compare names, columns, constraints, 133 valid/ready indexes, 51 enabled triggers, RLS, owners, ACLs, and policies. Do not bulk-copy the rows. Reconcile any source-versus-hosted objects before candidate acceptance.                                       |
| 114-row migration history                              | Preserve a restricted, read-only evidence snapshot under parent custody. Candidate ledger is produced by its own 139-file replay; never copy, synthesize, or repair old `statements`/rollback fields. The 25 pending files are applied only on the new candidate.                                       |
| 9 Auth accounts / 18 identities                        | Replace with new synthetic personas using candidate-only Auth configuration and fresh IDs, after the schema replay. Do not copy identities, OTP secrets, sessions, or credentials. Recreate only the role/profile links required for synthetic journeys.                                                |
| Private `vendor-intake-media` bucket / 0 objects       | Recreate bucket configuration and access policies on the candidate; no objects to copy. Verify private access and an empty object inventory.                                                                                                                                                            |
| 26 `platform_config`, 12 flags, 9 commissions, 3 zones | Start from source migration fixtures. Compare key inventories and values privately to old staging; stage any intentional staging-only overrides as a reviewed, explicit allowlist. Never publish values in CI artifacts. Keep sending/provider flags off until separately approved.                     |
| 79 private rate-scope rows                             | Treat as ephemeral synthetic rate state and let it expire or replace with new test counters. Do not import old rate or OTP attempt state.                                                                                                                                                               |
| 314 policies, roles and ACLs                           | Recreate through migrations and platform bootstrap. Compare effective grants, owner and definer metadata, policy expressions, RLS enabled/forced states and default privileges. The 6 nonstandard table ACLs and 6 intentional NOT VALID checks need source-specific review, not blanket normalization. |
| Active `send-sms-otp` Edge Function                    | Preserve the existing staging function and its settings on the old plane. Build candidate function from reviewed source with candidate-only secrets, but do not deploy/activate or invoke it until approved. No live SMS or other notification test is authorized here.                                 |

## Candidate acceptance sequence

1. Parent operator confirms an approved isolated no-cost target, scoped access,
   and absence of writers. The old staging plane stays untouched; obtain scoped
   recovery proof before any destructive action or cutover. Keep the existing
   114-row history snapshot restricted; never put stored SQL, user records,
   function bodies, or secrets in CI artifacts.
2. Pin source commit/tree and the 139 migration SHA-256 inventory. Capture
   candidate PostgreSQL image/extension inventory and compare with actual hosted
   staging, including `pg_trgm` and the patch-image difference. Stop on an
   unreviewed compatibility gap.
3. Replay all 139 files on the candidate without demo seed. Run the existing
   qualified disposable profile and its synthetic owner/ACL/config/fixture
   comparisons; record only group hashes and assertion status. Then separately
   compare the candidate catalog with the restricted old-staging survey. That
   earlier survey counted 76 source-qualified identifiers in 24 pending files;
   the additive ACL migration is the 25th pending input and requires a fresh
   candidate comparison. The earlier survey found 37 existing
   relations plus 4 functions, 35 absent identifiers, 214 constraints, 133 indexes,
   51 triggers, and 99 relevant policies. A lexical scan cannot cover dynamic
   SQL or data upgrades, so inspect those paths and run targeted synthetic
   upgrade fixtures before signoff.
4. Restore only approved source fixtures and new synthetic identities; verify
   zero external sends/transactions, bucket privacy, role isolation, and
   owner-scoped buyer/vendor/admin journeys. Keep all evidence sanitized and
   ephemeral; 3-day CI artifact retention and guaranteed stack cleanup apply.
5. Parent performs an independent diff review and prepares an explicit cutover
   plan for API/app Auth URLs, function bindings, writer pause, rollback and
   observation. Do not switch traffic or retire old staging until that plan is
   separately approved.

## Preservation upgrade and recovery decision

The clean candidate above replaces mock identities and transaction rows. If the
goal is instead to **retain the current 114-row six-column ledger and mock data**,
the next operation must be a rehearsal on a separately isolated, restore-tested
copy of staging `iyasmrmbcrvlfxpzescb`. No such no-cost recovery destination or
restore proof has been verified. This is a blocking resource and operator decision,
not a reason to use the shared Hetzner 4 GB production/n8n host or reset staging.
The restricted 114-row evidence remains with the parent; the application plan
uses version identifiers and custody-held digests, never a new export of stored SQL.

After a destination, scoped access, and restore proof are approved, the operator
freezes the exact source commit/tree and 25-file SHA-256 inventory. On the
**isolated copy only**, verify the 114-version ordered prefix and all six ledger
columns against the parent-held receipt; verify catalog and mock-data counts,
owners, ACLs, extension versions, and source compatibility. Inventory every
staging-only writer, including API/background jobs, schedules, n8n integrations,
Auth hooks, and the active `send-sms-otp` function. Pause those writers and
confirm in-flight work has settled before taking the copy/restore checkpoint.
Do not pause production writers or invoke notifications or providers.
Before applying a file, verify the six-column ledger's nullability, defaults,
keys, and insertion behavior against the chosen migration executor on the copy.
The pinned CLI's native three-column insert alone is not evidence that an
arbitrary hosted six-column row will be recorded correctly. Stop if the added
columns require an unreviewed value or if the executor would normalize earlier
statement arrays; do not fill fields with invented metadata or use migration
repair to make a failed application appear complete.

Apply the 25 reviewed files in three explicit phases on that isolated copy:

1. Apply source indexes **114–129** (16 prerequisites), from
   `20260921155234_atomic_cart_merge.sql` through
   `20260929120002_funded_service_completion.sql`. After each file, require one
   new truthful history version and exact preservation of the preceding six-column
   rows, including array bytes and bounds. Stop on any mismatch or unexpected
   data/catalog change; never mark a failed file applied.
2. Apply index **130**,
   `20260929120003_adopt_existing_service_obligations.sql`, through the existing
   guarded adoption helper. Its transaction must restore authority metadata,
   record the original immutable body once, and preserve prior history and mock
   economic rows. Ambiguous rows stay held for review; no synthetic ledger repair.
3. Apply indexes **131–138** (eight remaining), from
   `20260930170000_reconciliation_report_versions.sql` through
   `20261006160000_service_table_acl_hardening.sql`. Check exact 139-version
   order, unchanged 114-row prefix and intervening six-column rows, relevant
   data invariants, and the reviewed catalog, owners, ACLs, RLS, and configuration.

Only after that rehearsal passes may the parent propose a separately authorized
staging change window. At that window, pause the same staging writers, verify
the live 114-row receipt and recovery checkpoint under restricted custody, then
run the reviewed phases one at a time with stop gates. Resume staging writers
only after final 139-row and application checks pass. If a phase fails, keep
writers paused, retain the failed database for diagnosis, and restore the
approved recovery copy to a separate destination before any route switch.
Never reset the current staging database, overwrite its ledger, replay a file
whose committed state is uncertain, or permit simultaneous writers on old and
recovery destinations. A cutover or rollback route switch needs its own approval.

## Remaining decisions and permissions

The parent still needs authorization for a target resource and candidate
Auth/account replacement. Restricted backup custody and restore proof are
required before any destructive action or staging cutover. Candidate Edge
Function deployment and secrets, and any staging cutover, require separate
authorization. The current request
permits the source work and proposal only. No current database rows, hosted
configuration values, credentials, or provider outcomes have been copied into
this document.
