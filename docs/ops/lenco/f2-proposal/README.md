# F2 forward migrations and review boundary

The four executable proposals have moved to their coordinator-reserved canonical
paths below. Their original bytes remain in the earlier sealed handoff/history.
There is one executable SQL definition per change in this candidate.

| Order | Canonical path                                                                  | Purpose                                                                                                |
| ----- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1     | `supabase/migrations/20260929120000_service_payment_obligations_and_claims.sql` | Durable obligations, valid-link predicates, scoped locks, initiation claims, terminal failure evidence |
| 2     | `supabase/migrations/20260929120001_service_collection_settlement.sql`          | Atomic receipt allocation, canonical card proof, late-money exceptions and refund-gate coordination    |
| 3     | `supabase/migrations/20260929120002_funded_service_completion.sql`              | Acknowledgement separated from genuine funding, commission and atomic release                          |
| 4     | `supabase/migrations/20260929120003_adopt_existing_service_obligations.sql`     | Metadata-only adoption and durable ambiguity holds                                                     |

Allocation is #716/5885685575, reaffirmed by 5886861185. No optional `120004`
migration is needed: the shared scope helpers are dependencies in `120000` and
the Python authority uses them. Reservations are not SQL approval or permission
to apply migrations to a shared database. The coordinator rechecks the reservation
and migration tip before any publication. No published migration was amended.

## Scoped protocol

All claims, collections, failure-evidence writes, metadata creation/adoption and
service completion enter `lock_payment_checkout_scope`. It locks every valid
linked checkout in UUID order, then payments in `(checkout_group_id,id)` order.
The original checkout anchors the scope, including concurrent legacy adoption.
Writers next lock relevant orders in UUID order, then the existing per-order
`order_escrow:` advisory gate. Cancellation uses the same helper before its order
row, authority check and financial decision. No marketplace-wide lock exists.

The existing refund decision uses only `order_escrow:` and the money-gate row; it
does not acquire checkout/order locks afterward. Collection now also takes that
gate before deciding between allocation and a refund/terminal exception. F1
reservation/dispatch ownership remains separate; F2 requested notification of
any new inverse order in F1-owned reservation code. No such code was changed here.

A valid service link requires the same buyer across order, checkout and job,
the accepted job quote and vendor relationship through the service-deposit item,
the obligation amount matching its checkout, and distinct balance/deposit scope.
Wrong-owner or unrelated links cannot import another customer's funding.

`order_has_collected_money` is deliberately **not** a sufficient-funding predicate.
It includes relevant valid receipts and durable collection exceptions, preserving
the original-checkout conservative success guard for legacy/product/event orders.
Completion separately requires the exact full receipt-backed amount, canonical
card evidence, snapshot arithmetic and holds. COD behavior remains explicit.

For a funded cancellation, `refund_path` is an intent flag, not authority. Only an
actual order-vendor owner or persisted admin/superadmin role can enter that path;
the actor is rechecked under lock. The transaction reserves the existing refund
gate when appropriate and records `order.financial_resolution_required`. It does
not decide entitlement, submit a refund or pretend a refund succeeded. A customer
cannot bypass the guard with `refund_path=True`. Pending/unknown attempts remain
reconcilable after cancellation and receive durable resolution audit evidence.

## Historical evidence and rollback

Adoption never backfills payments, receipts, ledger entries or canonical card
query timestamps. Ambiguous/malformed spines create a durable
`service.obligation_adoption_held` audit record. Legacy fabricated cash remains an
unresolved discrepancy; no migration rewrites it. Historical card receipts need a
fresh canonical query before final service release. F3 must include those rows.

Rollback is forward-only for evidence: stop affected new initiation, revert
callers if needed, and preserve obligations, receipts, exceptions and postings.
Deployment rollback cannot reverse actual provider money.

## Execution and policy references

- `docs/ops/lenco/f2-hosted-acceptance.md`: exact isolated fresh/upgrade path.
- `docs/ops/lenco/f2-required-nodes.txt`: 35 required parameter-expanded F2 identities;
  includes all original 13, opposing schedules and the F1 failure-poller contract.
- `docs/ops/lenco/f2-policy-to-test.md`: current behavior versus draft FP/Q clauses.
- `policy/CONVERGEO_FINANCIAL_POLICY_DRAFT_v0.1.md`: supplied DRAFT / NOT EFFECTIVE input.

Actual PostgreSQL/PostgREST execution and genuine type generation remain required.
A parsed SQL file or collected test is not execution. The existing 88-case gate,
HTTP harness, typegen and security infrastructure remain unchanged.
