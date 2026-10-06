# Clean staging rebuild proposal — decision only

Source reviewed: PR 718 `b38bffc67ab7317cfec0ccb4753fff47b46b226c`, tree
`273f29776793f18a226400fdd069998b64cb2af3`; the proposed additive ACL
correction brings the source inventory to 139. This document authorizes no
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

## Remaining decisions and permissions

The parent still needs authorization for a target resource and candidate
Auth/account replacement. Restricted backup custody and restore proof are
required before any destructive action or staging cutover. Candidate Edge
Function deployment and secrets, and any staging cutover, require separate
authorization. The current request
permits the source work and proposal only. No current database rows, hosted
configuration values, credentials, or provider outcomes have been copied into
this document.
