# F3 reconciliation and honest-certification preparation

Status: **REVIEWABLE INTEGRATION DRAFT / NOT CODE_ACCEPTED / NOT SANDBOX_VERIFIED**
Date: 2026-09-30

This packet prepares a pure reconciliation matcher and repairs the existing drill's
evidence rules. It performs no provider request, shared database mutation, workflow
activation, fee deduction, payout decision, source publication or deployment.

The 2026-09-30 continuation adds the runtime adapter/reader and daily-report wiring
on the current guarded source. Its HTTP fixtures are explicitly synthetic. No real
Lenco endpoint was called, and no provider-backed acceptance row was produced.

## 2026-09-30 integration boundary

The runtime path now has three separate responsibilities:

1. `payments/lenco/reconciliation.py` calls only the documented read endpoints
   `GET /accounts` and `GET /transactions`. It selects the configured account,
   requires its currency, walks every declared `meta.currentPage/pageCount` page,
   hashes each raw response, and rejects a false envelope even when HTTP is 200.
2. `payments/reconciliation_reader.py` uses the server-held service-role client to
   page the protected receipt, exception, transfer, refund and ledger tables in a
   stable order. It binds platform-cash postings to actual domain and ledger IDs.
   Pending transfers are positions and never become paid movements.
3. The existing daily function in `payments/reconcile.py` feeds those observations
   into the pure matcher. The accepted F1 status poller in the same module is not
   changed. The report records run/source/schema/policy versions, UTC cutoff, raw
   input hashes, role, page manifest, stable matches and unresolved evidence.

The provider transaction feed documents a Lenco reference in `narration`; the
adapter labels that derivation as `transaction.narration`. It does not manufacture
a merchant reference, business movement kind, fee, reversal, settlement, opening
balance, actor, leg or rail. A missing/invalid row makes its page incomplete.

The existing `0018_reconciliation_reports.sql` schema permits one row per date.
Until a forward migration is allocated, a rerun with the exact same input
fingerprint returns the original row; a different or old unversioned input raises
an explicit immutable-report conflict. It never updates or deletes prior truth.

### Forward migration proposal (unallocated; no filename)

The single migration allocator should review an additive report-version table (or
an additive relaxation of the existing date uniqueness) with:

- immutable `run_id`, `report_date`, `prior_run_id`, `input_fingerprint`;
- source commit, schema/migration tip, matcher and draft-policy versions;
- configured account/currency, UTC cutoff and restricted evidence-object hashes;
- summary/discrepancy documents plus created-at and creating runtime role;
- uniqueness on the immutable fingerprint, never on date alone;
- service-role-only inserts and no update/delete path; admin read under RLS.

This proposal does not assign a migration identity and does not amend published SQL.

### Minimal financial-CI inventory

These are additive F3 nodes; they do not replace the accepted 88, F1/F2 or other
financial manifests.

| ID           | Pytest node                                                                                                         | Evidence                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| F3-HTTP-01   | `tests/test_lenco_reconciliation_adapter.py::test_adapter_selects_configured_account_and_walks_every_declared_page` | loopback HTTP / synthetic provider |
| F3-HTTP-02   | `tests/test_lenco_reconciliation_adapter.py::test_missing_pagination_meta_is_incomplete_not_assumed_single_page`    | loopback HTTP / negative           |
| F3-HTTP-03   | `tests/test_lenco_reconciliation_adapter.py::test_200_false_envelope_and_wrong_account_fail_closed`                 | loopback HTTP / negative           |
| F3-HTTP-04   | `tests/test_lenco_reconciliation_adapter.py::test_schema_error_is_retained_on_the_page_and_cannot_certify`          | loopback HTTP / negative           |
| F3-READ-01   | `tests/test_reconciliation_reader.py::test_reader_uses_receipt_and_ledger_linkage_and_keeps_pending_separate`       | local reader unit                  |
| F3-READ-02   | `tests/test_reconciliation_reader.py::test_card_without_canonical_verification_is_unresolved`                       | local reader negative              |
| F3-READ-03   | `tests/test_reconciliation_reader.py::test_reader_rejects_non_service_role_and_repeated_postgrest_page`             | orchestration negative             |
| F3-REPORT-01 | `tests/test_f3_reconciliation_daily.py::test_daily_report_is_source_bound_noncertifying_and_immutable`              | daily wiring unit                  |
| F3-REAL-01   | `tests/real_stack/f3_reconciliation_real_stack.py::test_f3_reader_authorization_linkage_and_immutable_report`       | required PostgreSQL/PostgREST      |

`F3-REAL-01` must run by exact path and pass; it cannot be replaced by the eight
unit nodes, aggregate totals, a skip or the synthetic cassette.

## Source and ownership boundary

The prepared tree was composed locally from these retrieved inputs:

| Input                              | Exact identity                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Refreshed guarded source           | commit `deb625caf86ba870eef85c877d65b4b37872fdcb`; tree `32aea25707f9e87eb02fd545356a230beb32bfd3`       |
| Preserved F3-only input            | 161,085 bytes; SHA-256 `5912bc42db090ca86f9f952fdc3b32f697e52047d2c50a59f8ffa9b374679f77`; eight paths   |
| F3 preparation on refreshed source | local commit `fca5e5ef600f7a0e484b80238a28d319806ef8fa`; tree `a2f4002c625d8d29f7044afebb59f2f86da775ab` |
| Superseded cumulative              | explicitly not applied; it contains obsolete F1/F2 source                                                |

The owner-reported F2 head `703dae6d35a6ef08eeb972b11b8461bd2d996002`
is a handoff identity, not a recovered or accepted remote commit. The coordinator's
later accepted source already contains the reviewed F1/F2 runtime and granted F3 a
review-draft-only handover of the daily-report portion of `payments/reconcile.py`.
F3 still does not modify F2 SQL/state, payout/retry behavior, CI, generated types,
dependency locks, n8n exports or live workflows. Publication and financial
acceptance wait for independent source review and coordinator composition.

## Pure matcher contract

`services/api/app/services/payments/reconciliation_matcher.py` has no HTTP or
database side effects. Callers must supply observed data without filling gaps from
request intent.

### Provider account and pagination

- Select exactly `LENCO_ACCOUNT_ID`; a missing, duplicate, wrong-currency or
  first-account fallback is an error.
- Freeze a timezone-aware UTC cutoff.
- Record every page number, cursor, next cursor, declared page count and total.
- Missing, repeated, out-of-order, failed or uncollected pages make the observation
  incomplete.
- Deduplicate only byte-equivalent movements with the same stable provider ID.
  Conflicting duplicates are evidence errors.
- Retain movements after the cutoff separately. They are not silently moved into
  the report period.

Supabase/PostgREST range pagination remains zero-based and inclusive and depends on
stable ordering. The F3 provider walker is not implemented in this packet because
the canonical Lenco endpoint uses its own `page`/`meta` contract. The eventual
runtime adapter must bind those actual pages into this pure contract.

### Movement matching

Match precedence is:

1. stable provider transaction ID;
2. provider/Lenco reference when unique;
3. merchant reference when unique.

Free-text narration is never a join key. Two different provider transaction IDs
with the same merchant reference remain two movements. If stable IDs are missing,
that repeated reference is ambiguous rather than guessed. Local order allocations
sharing one accepted collection are aggregated by a durable movement group while
all allocation, ledger and domain IDs remain in the report.
Each supplied ledger transaction must also carry its observed domain linkage; a
missing or unrelated linkage fails before matching rather than becoming a paid
movement by reference alone.

The prepared local input supports these categories independently:

- product collection and its per-order allocations;
- service deposit and service balance obligations;
- vendor payout;
- refund payout;
- quarantined collection exception;
- unparsed/unmatched movement.

An unparsed row is an explicit unmatched row, never discarded.

### Balance bridge

The bridge reports, in integer ngwee:

`opening funds + settled credits - evidenced fees - successful vendor transfers - successful refunds + evidenced reversals`

Unsettled credits and disputed positions are separate fields. When the supplied
credit basis is already net of fees, fees are not subtracted a second time. Missing
fee amount or reversal evidence is unresolved, not zero. The bridge compares both
provider ledger balance and available balance. It rejects a statement whose
account/currency differs from the configured target or whose immutable statement
identity/source hash is absent. Neither balance authorizes an unrelated liability
or payout.

### Q5 cost evidence

`calculate_proposed_cost_evidence` only demonstrates the draft v0.2 arithmetic:
the lower of evidenced unrecovered attributable cost and a proposed 5% ceiling of
the refundable paid amount. The result is always `enabled=false`. Missing cost
evidence produces no deduction number. Seller/platform failure and other mandatory
zero branches return zero. The illustrative 3% is not encoded.

Fee identity, source movement, original amount, reversal, prior recovery and
recoverability evidence are preserved. A later reversal is a corrective obligation,
not deletion of the prior report.

### Q6 decision evidence

The helper exposes obligation, configured account/currency, UTC snapshot, released
liability, available balance, active holds, KYC, immutable destination, durable
dispatch claim, provider settlement and order-release evidence. It returns missing
inputs only; it does not decide eligibility or dispatch. Provider settlement,
business release and transfer success remain separate facts.

## Exact 24-row evidence schema

Every row also requires `candidate_sha`, `deployment_id`, `schema_id`, UTC
`observed_at`, `verdict`, `origin` and `simulated`. `PASS` rows marked simulated,
source/local/CI-only, skipped, xfailed, missing or not-run cannot produce full
certification.

| Row | Acceptance case                     | Additional required identities                                                                          |
| --: | ----------------------------------- | ------------------------------------------------------------------------------------------------------- |
|   1 | MTN successful collection           | actor, rail, merchant/provider refs, receipt, checkout, ledger transactions                             |
|   2 | Airtel successful collection        | actor, rail, merchant/provider refs, receipt, checkout, ledger transactions                             |
|   3 | Failed collection                   | actor, rail, merchant/provider refs, provider transaction                                               |
|   4 | Timeout then polling/reconciliation | actor, rail, merchant/provider refs, provider transaction                                               |
|   5 | Duplicate webhook                   | actor, rail, merchant/provider refs, receipt, ledger transactions                                       |
|   6 | Invalid webhook signature           | actor, rail, checkout; controlled staging observation                                                   |
|   7 | Callback/poll race                  | actor, rail, merchant/provider refs, receipt, ledger transactions                                       |
|   8 | Amount/reference/provider mismatch  | actor, rail, merchant/provider refs, checkout                                                           |
|   9 | Successful hosted card              | actor, card rail, merchant/provider refs, receipt, ledger transactions                                  |
|  10 | False client card success           | actor, card rail, checkout; controlled staging observation                                              |
|  11 | Product paid order                  | actor, rail, merchant/provider refs, receipt, order, ledger transactions                                |
|  12 | Paid service/RFQ                    | actor, rail, deposit/balance leg, merchant/provider refs, receipt, job, obligation, ledger transactions |
|  13 | Paid event/ticket                   | actor, rail, merchant/provider refs, receipt, order, ledger transactions                                |
|  14 | Cancellation before collection      | actor, rail, checkout, order; controlled staging observation                                            |
|  15 | Late collection                     | actor, rail, merchant/provider refs, collection-exception and order IDs                                 |
|  16 | Refund-as-payout                    | actor, rail, merchant/provider refs, refund, payout and ledger IDs                                      |
|  17 | Vendor payout                       | actor, rail, merchant/provider refs, payout and ledger IDs                                              |
|  18 | Payout failure/recovery             | actor, rail, merchant/provider refs and payout ID                                                       |
|  19 | Reconciliation discrepancy          | configured account, immutable report version and ledger IDs                                             |
|  20 | Repeated receipt/idempotency        | actor, rail, merchant/provider refs, receipt and ledger IDs                                             |
|  21 | Ledger balance                      | configured account, immutable report version and ledger IDs                                             |
|  22 | Escrow release                      | actor, domain leg, order and ledger IDs                                                                 |
|  23 | Platform commission                 | actor, domain leg, order and ledger IDs                                                                 |
|  24 | Provider/account reconciliation     | configured account, immutable report version, provider transaction and ledger IDs                       |

Provider-backed rows accept only provider-origin sandbox/staging/production
classification. Rows 6, 10 and 14 may use controlled staging negative evidence.
Aggregate totals are derived output, not proof of these identities.

## D6 drill corrections

The canonical drill now enforces all eleven documented corrections:

1. Initial collection status must not already be `success`.
2. Product collections require one `escrow_hold` per actual order; legacy
   `charge_received` is not substituted.
3. Actual persisted `escrow-hold-{order_id}` keys are counted.
4. Webhook replay compares every relevant collection ledger transaction, not the
   charge count reused under another label.
5. Vendor payout accounting is queried by supplied payout ID.
6. Escrow includes both checkout-linked funding and order-linked release/refund.
7. A post-release refund requires its real clawback phase.
8. Refund input uses `customer_rail`.
9. Missing admin evidence blocks; refund/payout must both be terminal and linked.
10. Fresh negative and positive card identities are separate; positive requires
    provider/server verification, one receipt and ledger evidence.
11. A live top-level `PASS` requires all harness steps plus all 24 evidence rows;
    skip/missing/xfail/not-run cannot be hidden by aggregate counts.

The bundled cassette is explicitly synthetic and may only prove these assertions
react to mutations. It cannot populate a live 24-row file.

## Immutable report version

The runtime report writer must create, never replace, a version containing:

- report version/ID and prior-version link;
- candidate, deployment, schema/migration tip and matcher version;
- configured account and currency;
- UTC cutoff, page/cursor manifest, stop reason and raw-input hashes;
- provider/local movement stable IDs and evidence origin;
- match, ambiguity, unmatched and late-entry results;
- balance bridge and unresolved fee/settlement facts;
- all 24 evidence rows and verdict issues.

An existing daily report is not deleted to obtain a new result. A correction is a
new version linked to the prior report.

## Adversarial golden fixtures

`scripts/drills/fixtures/f3_reconciliation_goldens.json` is labelled
`SYNTHETIC_HARNESS_ONLY` and includes controls for:

- wrong account and currency;
- omitted/repeated page and conflicting duplicate ID;
- repeated merchant reference with distinct receipts;
- ambiguous mapping without stable IDs;
- provider fee reversal;
- late collection beyond cutoff;
- missing fee evidence;
- incorrect ledger linkage;
- per-order aggregation and explicit unparsed movement.

These tests are executable local evidence for matcher behavior only.

## Final integration checklist

1. Independently review this F3-only integration delta against the refreshed
   guarded source and confirm the F1 poller block remains byte-identical.
2. Allocate and review the forward immutable-report migration separately; do not
   rewrite migration `0018` or any published migration.
3. Run the explicit F3 real-stack module with the accepted combined source and
   capture checkout, database, PostgREST, role, schema, JUnit and report hashes.
4. Run the six F1 and 39 F2 required real-stack identities, all 755 related identities, the
   unchanged 88-case gate and F3 database cases on fresh and upgrade databases.
5. Run the live drill only after authorized sandbox origin/account/webhook/card
   fixtures are confirmed. Attach per-row evidence; no manual success fabrication.
6. Keep fee deduction and n8n activation disabled until separate policy,
   provider, source, deployment and operator approvals exist.

## Remaining provider facts

- authoritative sandbox REST origin and account binding;
- complete transactions pagination semantics and stable ordering guarantees;
- merchant-specific collection/card/transfer fees and fee reversal representation;
- settlement timing, opening-funds and available/ledger balance semantics;
- transfer pending/failed/not-found fixtures and safe failed-reference procedure;
- whether every status response supplies debit account and destination identity;
- hosted-card positive evidence and webhook registration/delivery;
- delayed-success fixture for a genuine late collection.

Without those facts, the matching source can be reviewed but provider-backed rows
remain `NOT_RUN` or `BLOCKED`.

## Real-stack execution request

Use a dedicated migrated PostgreSQL 17/PostgREST database and non-superuser roles.
Bind the application service client to the same database, retain checkout SHA/tree,
schema tip, role identity, JUnit and raw report artifact hashes. Then run from
`services/api`:

```sh
uv run --no-sync pytest -q -o xfail_strict=true -rA \
  tests/real_stack/f3_reconciliation_real_stack.py \
  tests/test_reconciliation_matcher.py \
  tests/test_lenco_reconciliation_adapter.py \
  tests/test_reconciliation_reader.py \
  tests/test_f3_reconciliation_daily.py \
  tests/test_lenco_sandbox_money_drill.py \
  tests/test_f1_payout_real_stack.py \
  tests/lane_d/test_f2_service_funding_postgrest.py \
  tests/lane_d/test_f2_cancellation_postgrest.py
```

The F3 real-stack module is deliberately outside ordinary `test_*.py` discovery.
The financial runner must invoke its exact path. It has no environment skip: a
missing database, PostgREST origin or JWT secret fails the case. It proves
service-role receipt/ledger reading, anon/authenticated denial, actual linkage,
report persistence, exact-input replay and append-only changed-input versions. The local
loopback HTTP tests prove transport/schema behavior with labelled synthetic
responses; they are not Lenco evidence.

The pure F3 modules do not themselves certify SQL locking or provider acceptance.
Database setup failure is a failure, not a skip waiver. Provider-backed execution
remains `NOT_RUN` until separately authorized sandbox credentials, configured
account identity and non-money read scope are supplied through the guarded runner.

## Allocated report-version continuation (review draft, 2026-09-30)

Allocation: #716 checkpoint 5914277388 reserves
`20260930170000_reconciliation_report_versions.sql`. This is a forward migration
for source review, not permission to execute it in a shared project. Migration
0018, its grants/RLS, legacy rows, financial SQL and F1 polling bytes are unchanged.

The normal daily consumer now calls `append_reconciliation_report_version`.
An RPC caller cannot select the run ID, version number or parent. The only
privileged writer is in an unexposed private schema; its public wrapper is
SECURITY INVOKER and EXECUTE is service-role only. All direct DML is revoked,
RLS is enabled/forced, and an immutable trigger rejects UPDATE/DELETE even for
a privileged fixture. Authenticated operators read only with the existing
database-backed `has_role('admin')` authority. No browser service key is involved.

The RPC canonicalizes and hashes configured account/currency/date/UTC cutoff,
full source SHA, schema/matcher/policy versions and all input hashes. Every
observed response/page and the protected local snapshot needs its SHA-256.
Missing statement, fee, reversal and settlement facts remain unresolved issues;
an observation with missing hashes cannot be silently stored as fully bound.
Exact replay returns the original immutable row, including a historical version
after newer versions exist. Identical inputs producing changed report content
are rejected: a reviewed source/matcher change must be bound explicitly.
Changed legitimate inputs append to that account/currency/date's chain. A small
report-stream row serializes concurrent append operations **after** HTTP reads;
no provider call or money-row/global marketplace lock occurs in that transaction.
Composite FKs and strictly decreasing parent version numbers prohibit
cross-account/currency/date links and cycles. Duplicate provider movements remain
the matcher's distinct deduplication concern, not a report-write side effect.

`ReconciliationReportStore.versions` performs explicitly scoped protected reads.
Its legacy reader labels rows `LEGACY_UNVERSIONED_ACCOUNT_UNBOUND`; it does not
invent account/source identity, silently migrate a clean legacy report or link
that report as a trusted parent. Legacy daily-fetch compatibility tests retain
their old boundary; the normal adapter consumer never writes the legacy table.
A report cannot authorize a payout/refund/release, buyer consent, new fees or
drill certification. Q5/Q6 and policy v0.2 remain DRAFT / NOT EFFECTIVE.

### Non-skipping isolated execution packet

Coordinator must wire this **separate** packet after independent SQL/source
review; no shared CI edit or generated db.ts is included here. Obtain new types
only through the already-qualified generator. Preserve the existing six/39/755
financial inventories and independent 88 gate; these seven F3 nodes are additions,
not replacement or inherited acceptance.

Prepare two runner-owned PostgreSQL 17 databases with the existing migration
replay/role/PostgREST harness (same pinned PostgREST). Names must be unique and
start with `f3_report_`; never use a shared project, `postgres` or a reused money
fixture database. Supply nonsecret source HEAD/tree, schema tip, versions and
SQL/REST role/binding evidence in the execution artifact. Keep JWTs/passwords
out of logs.

- Fresh database: replay reviewed migrations **including** 20260930170000.
  Configure `SUPABASE_DB_URL`, `F3_REPORT_DATABASE`,
  `F3_DISPOSABLE_REPORT_DB=1`, `LANE_D_POSTGREST_URL`, `LANE_D_JWT_SECRET`.
  SQL and REST origins must both be loopback, and SQL path/current_database
  must match the declared name. The tests use the existing service-client
  harness and verify each persisted random report ID in SQL, not HTTP totals alone.
- Separate upgrade database: replay the prior migration tip **excluding**
  20260930170000, then start its isolated PostgREST process. Supply
  `F3_REPORT_UPGRADE_DB_URL`, `F3_REPORT_UPGRADE_DATABASE` (unique prefix
  `f3_report_upgrade_`) and `F3_REPORT_UPGRADE_POSTGREST_URL` with the same local
  test JWT secret. The upgrade case inserts a legacy clean row **before** the
  new SQL, applies only this reviewed allocated migration and verifies the exact
  legacy row before/after plus protected HTTP persistence. Only a bounded
  PGRST202 schema-cache reload race is retried. No other failure is suppressed.
- Both databases require actual auth/users/roles, receipt/payment/ledger schema,
  the `rls_tester` membership/runtime checks and authenticator configuration from
  the existing harness. Test setup failure is FAIL, not SKIP. Start fresh disposable
  databases for reruns; the upgrade case intentionally rejects an already-migrated
  upgrade database, and never deletes reports to make a rerun pass.

From `services/api`, after those bindings exist:

```sh
uv run --no-sync pytest -q -o xfail_strict=true -rA \
  tests/real_stack/f3_reconciliation_real_stack.py \
  --junitxml=/tmp/f3-report-versions-real.xml
```

Exact required node suffixes (all under that module):

1. `test_f3_reader_authorization_linkage_and_immutable_report` — F3-REAL-01 retained;
   actual receipt/ledger reader, JWT denials and daily persistence/replay/append.
2. `test_report_versions_role_authority` — service RPC writer, explicit admin read,
   anon/nonoperator/operator/service direct INSERT/UPDATE/DELETE denial.
3. `test_report_versions_concurrent_exact_replay` — two concurrent HTTP clients,
   one version, one created result, no additional ledger transactions.
4. `test_report_versions_changed_inputs_and_historical_replay` — three retained
   versions, legitimate hash/matcher changes, old replay and unexplained truth denial.
5. `test_report_versions_partition_links_and_cycle_denial` — account/currency/date
   isolation, invalid parent constraint controls and immutable trigger.
6. `test_report_versions_missing_hashes_and_certification_denied` — incomplete
   hash/source/noncertifying controls through the actual RPC, with no written row.
7. `test_report_version_upgrade_preserves_legacy` — genuine separate pre-tip
   upgrade, legacy preserved byte-for-byte, honest reader label and no fake parent.

Acceptance: seven executed/passed, zero failures/errors/skips/xfails/missing,
source/schema-bound JUnit and SQL/REST evidence, alongside the unchanged regression
gates. The provider report inputs in these cases are explicitly synthetic; actual
SQL/HTTP tests do not prove Lenco facts or certify any of the 24 provider scenarios.
Local PostgreSQL/PostgREST execution remains NOT_RUN if these prerequisites are
absent. Collection and transport doubles are not locking/RLS certification.
