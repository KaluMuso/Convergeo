# NEW coordinator CI replacement proposal — independent review required

This source is a new proposal against continuity candidate
`f8cba729236c54200757f6f59ddf884df39a03fd`, tree
`609486ac019b0230d191e200a0658359be36a944`. It does not reproduce or inherit approval
for the missing 36,271-byte five-path patch SHA256
`96509bebfa39233b7b4ea17fa885ae0cda78dffe9cc4665f8ceb903ae65c3e75`.
Checkpoint 5924569051 describes that artifact but does not contain its bytes.
Available publisher, merchant and R2/F3 archives contain the older rejected
nine-path draft. That draft is reference only and was not imported.

The attachment's v3 patch was applied once to published 00863c24 in an isolated
checkout and reproduced the expected candidate tree. The genuine candidate
commit and ancestry were independently available through Git and authenticated
GitHub. Current canonical publisher refs are retained; this proposal belongs on
the separate deployment-disabled `codex/coordinator-ci-review-20261001` branch.
All four tracked possible Vercel project configurations explicitly disable that
branch without changing existing branch guards or production deployment settings.

## Retained contracts and proposed execution

| Gate | Binding / proposal |
| --- | --- |
| Financial | Existing runner, accepted127 baseline plus eight ordered additions, exact135 SQL inputs; six F1,43 F2,755 related in each pristine/upgrade phase. Existing seed/preservation probe and checked120003 helper invocation retained. |
| Critical | Existing independent88 runner, identity list and reconciliation unchanged. Review workflow checks out exact head SHA. |
| F3 | Seven unchanged mandatory identities: fresh135-input database plus separate131-input pre170000 database/REST. The seventh test seeds historical bytes before applying170000. The runner then applies only the three later SQL inputs and verifies surviving legacy bytes. No170000 or120003 double replay. |
| Merchant | Preserved26 DB and258 normal identities, six mounted UI names/files. Collection,Junit/Vitest reconciliation and process status all block. These checks do not prove the correlated buyer/vendor journey. |
| Curated/RLS | Existing required RLS context and its isolation contracts retained. Additional disposable gate collects full curated selectors and full tests/rls; supplies real REST/service and anonymous credentials; requires zero skips and retains both execution failures. |
| Type generation | Existing qualified Supabase 17.6.1.143/meta 0.96.6/CLI 2.109.1 generator, two identical outputs, genuine GraphQL/catalog qualification and zero-drift test retained. Provenance requires 135 inputs and records adoption-helper hash as well as the exact source/tree and GitHub event SHA. The fresh no-seed CLI reset does not invoke that helper; provenance states this explicitly and does not qualify fixture adoption. No db.ts is edited by this proposal. |
| Consumers/build | Review-branch CI selects exact head and forces complete workspace lint/typecheck/tests/build plus the existing bundle-origin guard. Ordinary branches retain merge-checkout semantics. |

New coordinator runners reuse existing financial command logging, timeout,
sanitization and JUnit helpers. Dedicated databases and containers are created
only after the repository's disposable GitHub host gate; source SHA, ancestry,
135 ordered checksums and all131 published SQL bytes are checked. Non-superuser
REST/browser/test roles, SQL/HTTP database identity and invalid/browser denial
are verified. Resource cleanup and PostgreSQL/PostgREST logs execute on failure.
Mounted API doubles remain labelled as such; no provider calls are made.

Broad no-DB Python collection excludes only the authz matrix, F1 real-stack and
merchant stock SQL modules with separate unconditional blocking owners. It does
not change their assertions or turn missing infrastructure into accepted skips.
Full identity/source hashes are recorded in coordinator-gate-inputs.json. That
manifest must be rebound after independently accepted corrections; counts alone
cannot authorize a source change.

## Guarded adoption and shared application remain separate

Local migration-replay and the financial accepted-baseline upgrade call
apply_service_adoption.py at120003. It checks immutable SQL and installed routine
body/authority before a transaction-local guard, restores authority before commit
and propagates psql failure. This proposal does not modify that implementation.

Hosted `supabase db push` does not invoke the repository helper. A fresh local
CLI reset has no legacy rows and cannot certify shared legacy upgrade reachability.
Before any shared application, the separately approved concrete plan must bind
the target, backup/restore identity, installed migration ledger, function owner/
body/grants, writer stop/drain state, one execution path through120003, subsequent
ordered SQL and rollback/forward-recovery limits. Running the helper then blindly
replaying raw120003 is unsafe. No shared ledger repair, migration application,
deployment settings change, merge, provider action or scheduler activation occurs.

## Independent inputs and evidence limits

Retain F3 source/SQL approval5923731625. Older financial/nine-path review5924838331
is REPAIR_REQUIRED; its verdict does not approve this proposal or the v3 adoption
helper. The v3 financial upgrade delta and merchant170100 still need their
allocated independent reviewers. No new financial/merchant verdict or qualified
135-input generated-output artifact was supplied/recovered at preparation time.
Therefore no accepted correction is invented or imported and no final integrated
certificate is issued. The coordinator remains the sole publisher; other lanes
return artifacts for additive composition and subsequent exact-SHA qualification.

Local command controls, pinned Ruff/mypy and workflow/typegen negative controls
are source evidence only. Actual PostgreSQL/PostgREST,804-per-phase,F3,26DB/6UI,
curated/RLS,qualified typegen/zero drift and complete consumers/build execution
must be read from the exact published SHA's genuine Actions logs/artifacts.
The correlated merchant journey and all shared-target/provider/operational gates
remain NOT_RUN until their own evidence exists. Dates remain26Oct target/7Nov
contingency; handbook R2/G1 is open. No new deployed buyer/business capability.

First diagnostic source 090ba3ad produced real F3 seven-of-seven, zero-skip
evidence; financial execution stopped at a rate-limited PostgREST pull before
either phase ran. Neither is acceptance for a successor SHA. Gitleaks identified
eight generic-api-key false positives in the source-checksum inventory. Each was
verified against the actual source file. The additive scanner correction exempts
only those eight exact digest values AND that exact path; AWS/GitHub credentials
remain tested on the same path. The final review SHA requires fresh CI evidence.

The same first diagnostic run produced qualified 135-input typegen artifact
11163205579 (archive SHA256 9ab9a44cc4135e2162c5bd2050569ed5f39579ffcc48a287aec7847fdb1df519).
Its source/tree, all 135 input hashes, genuine runtime/catalog qualification and
two identical generated outputs were consumed and verified. Output SHA256 is
30cf81bcf82729a66d5770e4b7767e9a53b9f3fd068671d2310305e04c6a8625.
The committed-types drift check correctly failed with exit 1. No generated types
were edited: the typegen owner must supply the independently accepted correction.
Critical 88 and merchant 26 DB/258 compatibility/six mounted also passed at the
first diagnostic source; this does not certify a successor or the full journey.
