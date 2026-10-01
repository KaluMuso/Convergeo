# Guarded adoption and atomic migration history: local application proposal

This proposal addresses financial review F-02 and supplies real PostgreSQL
controls for F-04. It **does not approve or implement shared staging/production
application**. The shared deployment workflow must not run ordinary
`supabase db push --include-all` through pending `20260929120003` on an unresolved
legacy history. Its raw file bypasses the transaction-local ambiguity guard.

The original published authority and adoption files remain byte-identical:

| Input                                                       | SHA-256                                                            |
| ----------------------------------------------------------- | ------------------------------------------------------------------ |
| `20260929120000_service_payment_obligations_and_claims.sql` | `b41aea0c3d5655d219bf775761a03aeb529e542bf965ec01c1b8ea15381d9663` |
| `20260929120003_adopt_existing_service_obligations.sql`     | `9a06f01acfb190274228e41022c19edf0dad25520ac9f121856e5ae70375aa8c` |

## Application boundary

`scripts/ci/apply_service_adoption_disposable.py` renders a source/target/history
bound transaction, and executes only with explicit `--execute-disposable`.
Execution is limited to a uniquely named `ci_adoption_<nonce>_<label>` database
whose database comment identifies this rehearsal. It also verifies the existing
owned `convergeo-continuity-pg` container, its pinned image identity and exclusive
`127.0.0.1:54322` binding. No production DSN or hosted target option exists.
Connection-indirection environment variables are rejected.

The repository's disposable GitHub financial job may instead supply its actual
`${{ job.services.postgres.id }}` as `ADOPTION_REHEARSAL_POSTGRES_CONTAINER`.
That alternate must be a full Docker CID and pass the existing financial
runner's strict GitHub repository/runner checks, with `QUALIFICATION_SHA` equal
to the actual checkout HEAD. Its inspected CID, pinned image and published
54322 port must match. Only this disposable CI case accepts Docker's standard
`0.0.0.0`/IPv6 port publication; every database client still connects exclusively
to `127.0.0.1:54322` and requires the owned database namespace/marker. This is
hosted **disposable CI** proof, not an option to apply on a shared Supabase target.

The bound plan contains the checkout commit/tree, hashes of every current
migration, hashes of the existing guard and the new installer, the exact
disposable target/container binding, and the complete expected ordered history.
The commit/tree describe HEAD; actual file hashes bind uncommitted development
bytes. Final release evidence must be rerun at the final committed composition.

One psql connection uses `-X`, `--single-transaction` and `ON_ERROR_STOP=1`.
Within that transaction it:

1. Verifies the target database marker, server binding and reviewed migration
   ledger schema. The fixture uses the Supabase-compatible `version text NOT
NULL PRIMARY KEY`, `statements text[]`, `name text` shape. Missing history,
   unknown columns/types/primary key, aliases, holes, changed SQL or unexpected
   future versions fail closed.
2. Takes a transaction advisory lock and an exclusive lock on the history table,
   then compares the installed history to an exact prefix of the reviewed
   executed inputs. This ordering is repeated by competing wrapper connections.
3. Checks the installed historical routine body and execution/ACL metadata using
   the existing reviewed helper, including on resume. Different authority is
   rejected before replacement.
4. If the original adoption row is already present in that verified prefix,
   returns `ADOPTION_RESUMED_NO_SQL_REEXECUTION`. Otherwise captures the entire
   `pg_proc` row, routine definition/signature/owner and expanded ACL entries
   including grantor and grant option.
5. Executes the existing hash-pinned guarded helper. Its temporary ambiguity
   checks hold shared checkouts, foreign obligations and foreign deterministic
   balance checkouts; the original adoption DO statement executes unchanged.
   The original routine is restored before commit.
6. Compares the complete restored catalog to the captured catalog. Only after
   successful application/restoration inserts the original `120003` row into
   `supabase_migrations.schema_migrations`, then commits the whole boundary.

The adoption file is a single original DO statement. Its `statements` array
contains that exact original file text, and `name` is
`adopt_existing_service_obligations`. The ledger does not claim that the temporary
guard is the published migration, and is never inserted for failed adoption.
All other local fixture rows record original SQL that this rehearsal actually
executed; their whole-file array representation is **not evidence about physical
equivalence or CLI statement segmentation of existing hosted ledger rows**.

## Failure and concurrency behavior

A SQL error or lost backend before commit rolls back obligation metadata,
checkout additions, audit holds, function DDL and history insertion together.
This includes a failure after the history INSERT but before commit. A retry
starts from the verified prefix and applies the same boundary once. When commit
succeeds but the caller loses its response, a retry sees the truthful row and
does not execute raw adoption again.

Two instances of this wrapper serialize their history checks and produce one
application plus one resume. The wrapper's locks do **not** make arbitrary
concurrent raw `db push`, application writers or unrelated deployment tools
safe. An operator-approved maintenance/writer-drain and single installer remains
required for a shared application plan. A caller that selected pending files
before another installer committed must not subsequently execute its stale list.

## Real database rehearsal

Run from the repository with the normal installed API dependencies and psql:

```bash
source /workspace/.cloud-tools/convergeo-env.sh
services/api/.venv/bin/python scripts/ci/rehearse_service_adoption.py \
  --evidence-dir /workspace/continuity-evidence/adoption-final-source
```

The evidence directory must not already exist. The script refuses to replace
prior evidence or reset pre-existing databases. It creates unique owned
databases, replays the real 127-input baseline, seeds the existing eight legacy
cases before F2, applies the three actual F2 prerequisites, and adds a foreign
obligation collision fixture. It clones only its own template, tests each
challenge on separate databases, and drops only databases it created. It never
starts a provider, changes a hosted database or runs a payment dispatch.

The retained correction rehearsal has **23 passing runtime controls** on
PostgreSQL **17.6**, pgvector **0.8.0**:

| Control                               | Native assertion                                                                                                                                                                                                                         |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Eleven installed-authority challenges | Body drift, SECURITY INVOKER, changed search_path, PUBLIC/authenticated EXECUTE, service grant option, missing service EXECUTE, strict/leakproof/volatility/parallel changes reject; full catalog/economic rows/history remain unchanged |
| Normal success plus repeat            | Eight legacy cases and the foreign obligation are conserved; one hold per ambiguity; original catalog restored; one original adoption ledger row; repeat does not execute adoption                                                       |
| Different actual owner                | `supabase_admin` owner is accepted and retained with exact body/catalog/grantor ACL restoration                                                                                                                                          |
| Four failure/termination controls     | Deliberate SQL errors and termination of the owned backend after actual adoption writes, both before and after history insertion, roll back all rows/DDL/history; identical retry succeeds                                               |
| Two competing wrapper connections     | Exactly one applies and one resumes, with no duplicated holds/obligations/history                                                                                                                                                        |
| Changed installed history             | Original-file substitution fails closed with no adoption or attempted ledger repair                                                                                                                                                      |
| Changed ownership marker              | Target rejection makes no data/catalog/history change                                                                                                                                                                                    |
| Original raw adoption                 | The actual immutable DO reproduces SQLSTATE `23505`; failed raw execution records no migration and leaves no partially adopted state                                                                                                     |
| Drift on resume                       | Existing adoption history does not bypass authority metadata validation                                                                                                                                                                  |
| Completed ordered history             | All current migration inputs execute on disposable history; adoption is excluded from pending membership; wrapper resume changes no rows/catalog/history                                                                                 |

Snapshots are collected through fresh independent connections after the tested
connection exits. They include OID/signature, definition, `prosrc`, owner, all
`pg_proc` execution metadata, ACL/grantor/grant-option entries, existing payments,
receipts, postings/ledger transactions, order/item/service links, checkout rows,
jobs/quotes, obligations, audit evidence and migration history. The four economic
legacy cases and ambiguous cases preserve existing monetary and order evidence;
no canonical card verification or buyer acknowledgement is invented.

The local evidence contains summary/commands/runtime JSON, per-control full
before/after catalog/data records, original-source manifests and raw native
psql logs. It is implementation evidence awaiting independent review, not an
independent approval or a hosted acceptance result.

## What must be supplied before shared application

The release/coordinator owner and independent financial reviewer need to approve
an actual target-specific mechanism, rather than copy this local-only installer
onto production. That review must include:

- Exact reviewed source SHA/tree and immutable migration hashes; actual target
  identifier and current ledger/catalog/owner/ACL/schema evidence.
- Physical equivalence proof for every historical alias or existing row. The
  local canonical prefix is not proof that the reported production ledger's
  aliases or pending migrations are equivalent. Never insert fictional aliases
  or mark unexecuted SQL applied to make a comparison pass.
- A complete ordered application plan, handling the guarded `120003` boundary
  and truthful history atomically while excluding a second raw execution.
- Maintenance and writer/deployer/scheduler controls, operator responsibility,
  current backup and a demonstrated restore/forward-repair procedure.
- Final-source disposable rehearsal on representative, approved installed
  history, plus independent review of the plan, fixtures, actual catalog
  challenges, failure controls and exact-SHA artifacts.
- Explicit approval for the named shared target and the reviewed action, before
  migrations, deployments, money activation or production cutover.

F-04's missing native catalog/rollback proof is now supplied locally. F-02's
atomic mechanism is concrete and reviewable locally; shared application approval
remains blocked until the target history and application mechanism are reviewed.
The 26 October target and 7 November contingency remain unchanged.
