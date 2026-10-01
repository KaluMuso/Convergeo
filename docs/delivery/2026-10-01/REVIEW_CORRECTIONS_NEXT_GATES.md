# Review corrections and next gates — 1 October 2026

Production launch remains conditional on independent acceptance and target readiness. Review corrections change the candidate: read the latest PR #718 head SHA/tree before reviewing or qualifying it. Earlier PR/run identities are historical evidence. The implementation correction is commit `016aa19844e456307637b34a79f8b494bc6982e8`; subsequent handoff commits do not replace the need to verify the latest remote head.

The corrected migration inventory contains **137 inputs**. The earlier qualified 135-input artifact does not qualify this inventory. The coding session found Supabase CLI 2.109.1, but local generation is blocked: the pinned PostgreSQL image failed registration with `no space left on device` under Docker's vfs driver. GitHub Actions artifact downloads also received a proxy 403 after redirect. No generated types were adopted. The qualified CI job is the generation owner; the handoff below retrieves its actual output rather than running a competing generator or hand-editing types.

Corrections address financial adoption/authority safety and merchant stock authority/concurrency review findings. They require separate independent re-review of actual source and SQL. Passing local tests does not itself close source review, hosted qualification, shared migration or production approval.

Actual local checks at this handoff: **3,250 RLS**, **185 curated**, **26 retained merchant database checks plus 15 new real-database controls**, **23 adoption controls**, and **1,566 JavaScript tests** (278 Vendor,95 Admin,756 Customer,437 package checks). Exact source-bound logs and review evidence are retained privately. Do not treat these totals as hosted execution or reuse them after source changes without assessing affected validation.

## Parallel handoff prompts

Send each reviewer the latest correction diff and their original private review packet. Return bounded findings and downloadable evidence to the existing coordinator, who alone composes and publishes the review branch. Never attach private operational reports, raw logs, personal records or evidence archives to the public repository.

### Original financial reviewer

```text
Please independently re-review the corrections to your original Convergeo financial/F3 review. Read latest PR#718 head SHA/tree first; verify the supplied correction diff matches that source, and distinguish unpublished local bytes. Focus on every original finding, adoption authority/body/security/search_path/ACL checks, legacy fixture and ambiguity holds, transaction/rollback behavior and the new migration inventory. Current inventory137 requires qualified regenerated types and final-SHA qualification; older135 evidence is historical. Verify immutable published inputs remain intact. Return a finding-by-finding PASS/CHANGES_REQUIRED/BLOCKED disposition, exact reviewed hashes, targeted real execution/negative controls with timing and exits, and remaining shared-ledger application limits. Source review is separate from approval to apply migrations or launch. Do not change shared databases, publish a competing branch or approve your own implementation.
```

### Original merchant reviewer

```text
Please independently re-review the corrections to your original Convergeo merchant review against latest PR#718 head SHA/tree and its actual correction diff. Verify closure of each original authorization, stock writer, branch topology/frozen input, locking/conservation, immutable operation/retry and SQL authority finding; retain import/edit/UI protections. Examine the new migration inputs and real-database controls rather than treating prior26 acceptance checks as proof of new behavior. Return exact-source finding dispositions, hashes and independently executed concurrency/negative controls with timestamps, collection/exits/skips and remaining production assumptions. No rewriting shared CI/types, remote publication or shared stock/money mutations; return bounded findings to the existing owner. Source approval and production journey/application approval remain distinct.
```

### Dot — read-only production evidence

```text
First identify available authenticated tools; do not assume administrative MCP access. Read the private readiness attachments for exact production project IDs and history inventory, then refresh source/PR#718, effective Vercel roots/Git/build/deployment guards, variable NAMES/scopes only, API/auth origins, migration history/physical equivalence, writer owners and backup/restore evidence read-only. Preserve unknown fields and never infer equivalence from version/name/count alone. Latest corrected source contains137 inputs; coordinate with the existing coding owner for its sole pinned type-generation run, not a duplicate. Old135 artifacts and run status require source/timing reconciliation. Return a private timestamped/hashes-bound evidence packet and exact final production action/target/rollback/forward-repair proposal. No settings edits, fake ledger normalization, shared migrations, restore execution, live provider actions, messages, merge or deployment. Do not publish private attachments or raw evidence in the public repository. The final concrete application/deployment approval follows verified reviewed source, qualified types, hosted acceptance and recovery readiness.
```

### ChatGPT Work — retrieve qualified types

```text
Use authenticated GitHub access for KaluMuso/Convergeo. Read PR #718's latest head SHA/tree and find its exact-head CI run. Wait for the Database / typegen drift job's actual result; retrieve artifact generated-database-types-<that full SHA>. Do not use run36867728196's earlier135-input output as137-input qualification. Read provenance.txt, database-shape.txt, graphql-initialization.txt, db.first.ts and db.ts. Verify CLI2.109.1, pinnedPostgres17.6.1.143/server170006, vector0.8.2, pg_graphql1.6.1, pgcrypto1.3, postgres-meta0.96.6, schemaspublic/graphql_public, all137orderedinputhashes, real extension-owned GraphQL and relocated pgcrypto shape, and byte-identical two generated outputs. Record exact source SHA/tree, artifact ID/digest and db.ts SHA256. Return the unchanged generated db.ts and provenance as downloadable attachments to the existing coordinator, plus a types-only patch against that verified head. A drift failure is expected until the actual qualified generated bytes are committed; it is not permission to weaken the check. Do not publish a competing branch, hand-edit generated declarations or touch shared databases. If authenticated artifact retrieval is unavailable, state the exact missing capability; never claim generation from a filename or an empty download.
```

## Gate sequence

Review corrections and production discovery can proceed in parallel. The coordinator then composes accepted fixes, records final SHA/tree and 137-input manifest, adopts only deterministic qualified generated types, and obtains final-source hosted acceptance with exact collections and explicit skips. Target history equivalence, atomic migration-ledger application, writer maintenance and restore evidence must be independently reviewed before the concrete production action is approved. Source changes require affected evidence and approvals to be rebound.

GitHub CLI access is available to this coding session; operational service MCP tools are not. Existing planning dates remain unchanged. No production completion or new deployed capability is claimed by this handoff.
