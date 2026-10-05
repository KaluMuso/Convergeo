# Disposable migration adoption rehearsal and cutover contract

**Status: prepared only.** This document and its offline gate do not authorize a
database read, dump, restore, migration apply, deployment, or public release.
No source-row bytes, complete source custody, real backup receipt, restore
receipt, measured recovery time, or migration approval accompanied this patch.
The historical source used to prepare this packet was commit
`be85e77d72c05cb2e29aff14e730509c07d3ccb3`, tree
`0e1c2b360ce14e5b127ebbbf724d65f527ebe9aa` (draft PR #718). Rebind
the example manifest to a reviewed current commit and tree before any future
authorized rehearsal. That historical source had 138 SQL migration files.
Earlier sandbox evidence reported 114 history rows and 24 manifest-named
missing inputs; those counts alone do not
prove that the inputs or ledger bytes are now available. The proposed sequence
of 16 prerequisites, adoption, and seven remaining inputs is **provisional**.

This is the migration-specific companion to
[`deploy-verify-runbook.md`](deploy-verify-runbook.md),
[`runbook-disaster-recovery.md`](runbook-disaster-recovery.md), and
[`infra/ROLLBACK.md`](../../infra/ROLLBACK.md). The existing
`scripts/ops/restore-staging.sh` is unsuitable for this historical baseline:
its currency check demands the repository tip, its target rules cannot express
the required source/target binding, and its `--no-owner --no-privileges` restore
cannot prove owner or ACL parity. Do not relax that helper's safeguards or use
it as a receipt for this rehearsal.

## Immutable execution manifest (fill before a future authorized run)

Start from `scripts/ci/disposable-migration-rehearsal.example.json`; its null
source identity fields must be filled from the reviewed current commit. Keep the
filled manifest and evidence outside the repository under restricted custody.
Every blank value is a **stop**. Record the following alongside that manifest:

| Binding           | Required evidence                                                                                                                                                                                                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Source            | Exact commit, tree, draft PR head, 138-file filename/version/SHA-256 inventory, and the reviewed 24-input manifest with each file's byte hash. Recheck legitimate successor changes before binding.                                                                                                                                        |
| Historical ledger | Raw read-only snapshot of all six `schema_migrations` columns from the actual baseline, source database identity, full snapshot SHA-256, count, and exact rows. Preserve `created_by`, `idempotency_key`, `rollback`, stored SQL text, null versus empty arrays, dimensions and lower bounds. A count or list of versions is insufficient. |
| Backup custody    | Source plane, capture time, dump format/version, immutable object identity, size, SHA-256, access controls, chain of custody, and a witnessed restore. Do not infer a backup from a schedule or an OCI object name.                                                                                                                        |
| Configuration     | Non-secret source/target project or cluster identities, PostgreSQL/extension versions, role inventory, owner/ACL/default-privilege inventory, installer version and configuration digest, API/frontend image digests, writer and background-job inventory, and rollback candidate identities. Values of secrets stay outside evidence.     |
| Target            | A newly created local loopback database named `ci_migration_<12 hex>_<label>`, port 54322, with database comment `CONVERGEO_DISPOSABLE_MIGRATION_REHEARSAL:<database>`. Record creation receipt and prove it was absent beforehand. Never repurpose an existing database or use `postgres` as the target.                                  |
| Order             | A reviewed ordered list of 24 version/file/hash tuples, including adoption's exact position. The 16/adoption/7 partition is only a hypothesis until dependencies and physical state are checked.                                                                                                                                           |
| Recovery          | Independent baseline restore receipt, measured restore and verification durations, measured writer-drain time, elapsed apply/compatibility time, recovery point, and concrete RTO/RPO calculation. Existing 30-minute/24-hour targets are objectives, not measured proof.                                                                  |

The `source_snapshot_sha256`, `dump_sha256`, and
`migration_inventory_sha256` in the JSON manifest bind raw evidence. The gate
also recomputes the Git commit/tree and verifies the complete migration
inventory and every SQL file against the bound Git blob from `--repo-root`.
The file hashes are from Git blobs. A Windows checkout's CRLF conversion is
accepted; any other byte change or untracked SQL file is rejected.
Each `ordered_pending_inputs` entry must provide the version, filename, and
SHA-256 of a file in that inventory, in the reviewed application order.
It intentionally rejects the example's null fields. A source snapshot or dump
that cannot be lawfully obtained and verified is a blocker; **never synthesize
canonical history rows or fill them from migration filenames**.

## Future disposable-DB execution manifest

The following steps are instructions for a separately authorized operator with
an isolated, approved source and a private scratch database. None were run in
this preparation task. Store a timestamped, immutable receipt at each step.

| Step                       | Action and required receipt                                                                                                                                                                                                                                                                                                                                                                                                   | Stop condition                                                                                                                                   |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0. Freeze inputs           | Review exact source commit/tree, 24 file bytes, migration dependency graph, config and image identities. Check each SQL file for explicit transaction control or statements incompatible with transactional application. Sign the ordered plan.                                                                                                                                                                               | Any missing file, divergent successor, unknown dependency, or non-atomic input.                                                                  |
| 1. Establish custody       | Obtain separately approved source snapshot and full backup; verify hashes, completeness, role inventory, and PostgreSQL/extension compatibility. Capture `scripts/ci/disposable-migration-snapshot.sql` read-only from the source baseline. Protect row-bearing evidence as sensitive data.                                                                                                                                   | Missing live row bytes, incomplete dump, unknown owner/role mapping, or missing approval for copying data.                                       |
| 2. Restore baseline        | Create only a fresh, marked, loopback disposable target. Restore owner and privilege statements; provision reviewed roles before restore. Capture restore command, exit status, elapsed time, dump hash, target creation and marker receipt, and restored snapshot.                                                                                                                                                           | Any skipped owner/ACL entry, restore error, role mismatch, or snapshot difference. Do not use `--no-owner` or `--no-privileges` to make it pass. |
| 3. Prove baseline          | Run the offline verifier with the source, dump, restored snapshot, and filled binding. It compares all six columns, the unique idempotency key, array shapes, database/schema/relation/function/type owners and ACLs, column grants, and default privileges.                                                                                                                                                                  | Any mismatch. A 114-row count alone is not a pass.                                                                                               |
| 4. Pause and drain         | In the isolated rehearsal, stop all application, job, webhook, and migration writers. Record the pause mechanism, queue/in-flight counts reaching zero, and durable pause receipt. Hold the pause through **all** remaining migrations and compatibility checks.                                                                                                                                                              | An unaccounted writer or unverified drain.                                                                                                       |
| 5. Serialize graph         | Acquire one operator/installer mutex covering the **entire** graph, not only adoption. Prevent a second installer or Supabase CLI apply from racing. For each reviewed file, execute its original SQL and its truthful six-column ledger insertion in **one** database transaction, with `ON_ERROR_STOP`; use no blanket `ON CONFLICT DO NOTHING`, ledger repair, or fabricated statement array. Commit only if both succeed. | Any SQL/ledger failure, concurrent writer, unreviewed implicit commit, or history divergence. Stop and retain the database.                      |
| 6. Checkpoint every commit | After each successful transaction, extract an immutable ledger snapshot and command/transaction receipt. Run the offline verifier against all checkpoints accumulated so far. The next attempt may resume only from the exact committed prefix and original rows. Inject a failure in a separate disposable clone and prove SQL and history both roll back before claiming crash safety.                                      | Missing receipt, changed prior row, gap, duplicate, unexpected commit, or rollback failure.                                                      |
| 7. Verify remainder        | After adoption and seven remaining inputs, compare full physical catalog and data invariants against the approved expected state. Exercise API/frontend compatibility, money and Auth failure paths with synthetic fixtures, and rollback candidate compatibility while writers remain paused.                                                                                                                                | Any failed compatibility check, unexplained physical drift, or missing evidence.                                                                 |
| 8. Recovery trial          | Restore the bound baseline into **another** fresh scratch target from the same immutable dump; recheck history/owners/ACLs and application compatibility; measure elapsed recovery and data-loss window. Keep both disposable targets for review.                                                                                                                                                                             | No successful independent restore or measured RTO/RPO.                                                                                           |
| 9. Decision                | A distinct reviewer compares hashes, all receipts, actual vs planned sequence, writer drain, tests, recovery proof, and authorization scope. Only then can a parent-coordinated publication decision be requested.                                                                                                                                                                                                            | Any unresolved blocker or absent authorization.                                                                                                  |

### Offline preservation gate

The SQL extractor emits one JSON line. `psql -X -Atq -v ON_ERROR_STOP=1`
may be used **only by the future authorized operator**; this patch does not
run it. Keep each snapshot's raw bytes unchanged after hashing. The verifier
accepts checkpoint files in actual commit order, even when version sorting
interleaves pre-existing history rows:

```bash
node scripts/ci/verify-disposable-migration-rehearsal.mjs \
  --repo-root . --binding <private-binding.json> \
  --source <private-source-snapshot.json> --dump <private-dump> \
  --restored <private-restored-snapshot.json> \
  --checkpoint <private-after-first-commit.json> \
  --checkpoint <private-after-second-commit.json> # repeat through all bound inputs
```

The verifier accepts a committed prefix and reports the next expected version.
It checks each planned file hash against the checkout, but the independent
transaction receipt must prove those bytes were actually executed.
The verifier checks preservation and sequence evidence; it does **not** prove
that a snapshot came from a trustworthy database, SQL/history atomicity,
full data correctness, writer drain, or release readiness by itself. Those
need the independent receipts above. Snapshot extraction includes history SQL
and can expose sensitive data; do not add real snapshots or dumps to Git.

## Stop/go and rollback boundary

**Go for a rehearsal review** requires exact source/dump custody, baseline
parity, all ordered transaction/checkpoint receipts, writer pause/drain,
synthetic compatibility results, independent recovery, and measured RTO/RPO.
Until then the result is **blocked**, even if the offline gate returns green on
synthetic fixtures. A public cutover additionally needs its own approval,
production backup and restore proof, accepted data-loss window, exact image
and config identities, and parent-coordinated review. This document grants none.

On a failed rehearsal, stop the installer and keep writers paused; preserve
failed transaction logs and the last committed checkpoint. Restore the bound
baseline into a fresh disposable target and verify it before any retry.
Resume only at the exact committed prefix after root cause review. For a future
real cutover, an application rollback is valid only if the old code was tested
against the post-migration schema; otherwise the plan must include a separately
authorized data restore with a measured loss window and payment/Auth
reconciliation before writers resume. Never assume additive SQL alone proves
backward compatibility. No live rollback, merge, deployment, settings change,
or publication is within this rehearsal preparation.
