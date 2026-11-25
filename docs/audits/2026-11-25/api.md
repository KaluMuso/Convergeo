# Convergeo backend audit (services/api + n8n) — 2026-11-25

Read-only static audit of origin/master. No prod calls. Paths relative to repo root; `A:` = services/api/app.
Legend: **NEEDS-KING** = touches payments/escrow/ledger; not auto-merge.

Overall: the money core is well built. Findings: integer ngwee everywhere (Decimal at the Lenco seam, no float money found), HMAC-SHA512 webhook verification over raw body with compare_digest, unique-key dedupe, fail-closed "trusted evidence" check before processing, amount/currency/reference/provider-reference validation, atomic SQL settlement (`apply_prepaid_collection_success`: receipt + ledger + audit + outbox in one txn, with locks and keyed idempotency). The gaps are around the edges (stuck states, scheduling, alerting, rate limits, catalog perf).

## CRITICAL

### C1. Payment stuck in `initiated` forever after a definite Lenco rejection; customer cannot retry, order never cancels — NEEDS-KING
- A:services/payments/initiate.py:117 `except PaymentProviderError: return ... INITIATED, None` swallows every provider error (bad number/operator 4xx, 5xx, timeout) and returns HTTP 200 "initiated". (LencoClientError subclasses PaymentProviderError, so even definite validation rejections land here.)
- The row then has no way out:
  - `claim_payable_payment` (supabase/migrations/20260929120000_service_payment_obligations_and_claims.sql ~L180-190) blocks any new attempt unless the prior payment is `failed` with `raw.terminal_provider_failure=true` -> `payment.not_payable / unresolved_attempt` (409), and `/payments/retry` returns `payment.in_progress` (A:routers/payment_status.py:355).
  - `sweep_stale_payments` only selects `pay_offline`/`ussd_pushed` (A:services/payments/state.py:849-865), never `initiated`.
  - The 30-min poller selects `initiated` but Lenco returns NOT_FOUND for a collection it never created; it counts `errors += 1` and `continue`s every tick (A:services/payments/reconcile.py:419-427).
  - `unpaid-order-cancel` excludes any order with a payment not in (expired, cancelled, terminal-failed) (A:routers/internal_order_jobs.py:270-277), so the order stays `placed` with stock reserved indefinitely.
- Scenario: customer types 0971234567 or 097-123-4567 into `/payments/retry` (no validation, see H2), Lenco rejects, customer sees a spinner, taps retry, gets 409 forever. Same for a Lenco 5xx during initiate.
- Fix: in initiate, if the error is a definite pre-dispatch rejection (`dispatch_may_have_succeeded` false / validation category), call `record_collection_failure`-equivalent to set `terminal_provider_failure`, transition `initiated -> failed`, and return a 422/502 with a message key. For ambiguous outcomes keep in flight, but give the poller a rule: `initiated` + NOT_FOUND for > TTL (15 min) with the original dispatch recorded as ambiguous-and-not-found -> mark failed/terminal (Lenco is idempotent on reference, so a later success is still reconcilable via late-collection path). Add `initiated` to sweeper candidates.

### C2. Webhook processing depends on a drain tick that is NOT in the repo's n8n source of truth — NEEDS-KING
- `/webhooks/lenco` only verifies + stores + acks (A:routers/webhooks_lenco.py:51-105). Orders become paid only when `POST /internal/reconciliation/webhook-drain-tick` runs (A:routers/internal_reconciliation.py:~95).
- `infra/n8n/reconciliation.json` has only `poll-tick` (30m) and `daily-report`; `docs/ops/n8n-workflows.md` registry has no drain row; `door-poll-tick` also absent. The drain exists only in the live "combined" workflow, referenced by scripts/n8n/prepare-combined-repair-drafts.mjs:33 (30s) and the scrubbed 2026-10-05 export.
- Scenario: any re-import/restore from repo (DR drill, n8n rebuild, the "repair drafts" flow) silently drops the drain: MoMo confirmations fall back to the 30-min re-query poll; customers see "pending" for up to 30 min with real money taken. All 38 repo workflows are `active:false` and none sets `settings.errorWorkflow` (by design, instance-local), so nothing in repo proves the live state.
- Fix: add `infra/n8n/webhook-drain.json` (every 30s, `webhook-drain-tick`, 3x retry, error page via money-workflow-error-alert) and `door-poll` (2 min), add registry rows (test_n8n_registry.py enforces), document in n8n-activation-runbook. Founder must verify live workflow list matches (read-only export diff).

## HIGH

### H1. Customer money collected but order cancelled/expired -> exception row only, no alert, no refund path surfaced — NEEDS-KING
- `apply_prepaid_collection_success` returns `late_collection` (cancelled order, expired checkout, sibling success, duplicate provider collection) and writes `payment_collection_exceptions` + audit (migration 20261116100100_collection_coupon_funding.sql ~L160-200). Only reader is the daily reconciliation report (A:services/payments/reconciliation_reader.py:197). No outbox/admin/founder alert, no customer message. Also `claim_payable_payment` then blocks the checkout (`collection_exception`).
- Scenario: customer pays at minute 14 of a 15-min window while a 12h unpaid-cancel or admin cancel races, or pays twice by retry; money sits in Lenco until the next 05:00 report is read by a human.
- Fix: in the drain/apply path, when result == `late_collection`, enqueue a founder alert (outbox template or n8n tick `/internal/n8n/collection-exceptions/tick`) with metadata only, and surface in admin payments queue. Refund orchestration stays manual per policy.

### H2. `/payments/retry` (first MoMo initiation endpoint) accepts unvalidated payer number and has no rate limit — NEEDS-KING
- A:routers/payment_status.py:327-420: `payer_number` only `max_length=20`; `_normalize_payer_number/_is_valid_payer_number` from checkout_payment.py are not applied. `POST /orders` validates the number but never initiates; the client must call retry. Raw "097..." goes to Lenco -> C1.
- Rail defaults to `mtn` if no prior row and no body rail (L~390); wrong operator = failed push.
- No `bump_rate_counter` (see H3); each call can hit Lenco.
- Fix: reuse validators, derive operator from prefix when rail absent, add PAYMENT_WRITE enforcement.

### H3. Registry "covers" every mutating route but ~115 do not actually enforce a limit
- A:core/ratelimit_policies.py declares POLICIES + a startup coverage gate, but `policy_for` is never used by any middleware/dependency; the module doc says enforcement stays per-route. AST scan (route handler + same-file helpers + service helpers calling bump_rate_counter) finds 115 mutating routes with no enforcement, e.g.:
  - money-adjacent: POST /orders (A:routers/orders_create.py:416), POST /payments/retry, POST /payments/card/session and /{id}/verify (payments_card.py:653,712, `/verify` queries Lenco), /checkout/session, /checkout/steps/*, door-payment (order_delivery.py:203,224), disputes (5), order_confirmation (3), pickup_verify /verify (code brute-force surface, pickup_verify.py:87).
  - others: cart.py (7), account.py (8), kyc.py (4), kyc_media/media/listing_images signing, vendor_orders (6), ticket_types (6), admin_roles (5), admin_governance_ops (5), vendor_coupons, privacy, etc. Full list: scratchpad `unlimited.txt` (generated), grouped counts in section Batches.
- Fix (non-payment routes, auto-mergeable): add `Depends(enforce_registered_policy)` in ratelimit_policies.py that resolves `route_id(request)` -> POLICIES -> `bump_rate_counter` keyed by user id (fallback IP), fail-open only on limiter outage, apply as `dependencies=[...]` on those routes (or `APIRouter(dependencies=...)` per file). Payment routes get the same dependency in the NEEDS-KING batch.

### H4. Catalog PLP does full-table work on every request; breaks past a few hundred listings
- A:routers/catalog.py:366-379 `_fetch_search_documents` has no range/limit: PostgREST max-rows (default 1000) silently truncates the catalog; A:routers/catalog.py:795-803 `_build_candidates` then runs, on EVERY page/filter request (cursor is an offset into a recomputed list): `listing_images.in_("listing_id", ALL ids)` (A:services/listings/demo.py:123-128), `vendor_listings.in_("id", ALL ids)` with embedded relations (catalog.py:617-630), `order_item_products.in_("listing_id", ALL)` then `reviews.in_("order_item_id", ALL order items)` (catalog.py:693-712). `.in_()` of N UUIDs is a GET query string: ~38 bytes each, so ~200+ listings approaches typical 8KB URL limits (PostgREST/proxy 414/400); ratings list scales with order history, worse.
- No cache layer and no Cache-Control on `/catalog/listings`, `/products/*`, directory; only categories/config/home-feed use caches.
- Fix: (1) helper `chunked_in(query_factory, ids, size=100)` used for all `.in_` over unbounded id sets (233 `.in_` sites; start with catalog/demo/products/directory); (2) paginate search_documents with `.range()`; (3) cache the unfiltered candidate set per category_path for 30-60s via core/ttl_cache.py (Upstash/in-memory) and add `Cache-Control: public, s-maxage=30, stale-while-revalidate=120` for anonymous GETs; (4) compute ratings from a grouped view/RPC, not by shipping every order item id.

### H5. `/me/follows?limit=100` always 422
- Client: apps/customer/lib/engagement-api.ts:147. Server: A:routers/follows.py:48,192 `MAX_PAGE_SIZE = 50`. Every call (follow state / following page) fails validation. Other list limits checked from frontends (rfq 50, feed 24, deals, home rails, stream 6) are within bounds.
- Fix (either): server `MAX_PAGE_SIZE = 100` (one-line, safe; query is `vendor_id,created_at` + vendors lookup), or client limit=50 with offset paging. Prefer server bump + test.

## MEDIUM

### M1. Fee booking can be permanently skipped after a committed settlement — NEEDS-KING
- A:services/payments/state.py:710-712: `book_collection_fee` runs after the settlement RPC returned `applied`. If it raises (DB blip), the webhook row stays unprocessed and the retry sees `duplicate`/non-applied -> returns None before booking, so the Lenco fee is never booked (platform_cash vs Lenco drift appears later as a reconciliation diff). Fix: book fee idempotently on the `duplicate` branch too (idempotency key per payment already exists per docstring), or call it inside the RPC.

### M2. Webhook drain poison rows
- A:services/payments/reconcile.py:517-580: rows that raise (amount-mismatch hold, illegal transition) or return None (card success waiting for canonical verify, state.py ~L1085-1096) stay `processed_at is null` and are re-scanned every 30s forever, logging at warning each tick; with >200 such rows (limit 200, oldest first) newer events starve. Fix: stamp `attempts`/`last_error`, back off, and move to a `needs_review` state after N tries; alert on count > 0.

### M3. Alert log fields are dropped by the JSON formatter
- A:logging.py:30-33 serialises only `dependency, failure_kind, method, status_code, duration_ms`. Calls like A:routers/webhooks_lenco.py:62-68,80-88 pass `extra={"alert": "lenco_webhook_invalid_signature"|"..._missing_signature", "event_id", "flags"}`; those keys never reach the log line, so any log-based alert on `alert` is dead. Fix: allow-list `alert`, `event_id`, `flags` (non-PII). (Logging is otherwise PII-safe by construction.)

### M4. Cron endpoints fail silent (200 with zeros) when the DB script fails
- A:routers/internal_order_jobs.py:~270,~320 and similar: `result = run_sql_script(...); if not result.ok: return []` -> `scanned:0` 200 OK. n8n's outcome check passes while cancel-unpaid/auto-release do nothing. Fix: raise AppError 503 so n8n error workflow pages.

### M5. Internal tokens compared with `!=` (24 routers); only 2 use `compare_digest`
- e.g. A:routers/internal_order_jobs.py:93, internal_privacy.py:39, internal_review_aggregate.py:32. Fix: central `tokens_match()` in core/internal_token.py using `hmac.compare_digest`; mechanical replace. Strict-env fail-closed token resolution is good.

### M6. Public GET/POST handlers use the service-role client by default
- `get_supabase_client` returns service-role for catalog/products/directory/follows etc.; correctness relies on hand-written `.eq("status","active")` filters instead of RLS (catalog.py:620-630). Risk is a missed filter leaking draft/suspended data. Orders create correctly uses user client for the cart. Medium-term: public reads via anon client + RLS views.

### M7. Request-model strictness
- A:routers/orders_create.py:81,92, checkout_payment.py:45,54: `BaseModel` (lenient, ignores unknown fields) vs the CLAUDE.md "Pydantic v2 strict" rule; `PaymentMethodResponse.cod_eligible` (checkout_payment.py:~330) ignores coupon/gift/discount rules that `/steps/payment-options` applies, so the UI can show COD eligible then be rejected at order create. Fix: use StrictModel with the client's field set (verify apps/customer checkout payloads first), share one `_cod_eligible()` helper.

### M8. Sweeper never ends an unanswered MoMo prompt
- A:services/payments/state.py:925-962: `ussd_pushed`/`pay_offline` are only moved on Lenco failed/success; there is no expiry branch (SweepResult.expired is never incremented), so a prompt Lenco never resolves leaves the checkout blocked and the order held indefinitely. Add a hard ceiling (e.g. 24h) that flags for admin review (not blind expiry), consistent with the "never blind expiry" rule.

### M9. n8n hygiene / WAHA
- WAHA: only `waha-intake-sweeps.json` + `waha-intake-digest.json` (vendor intake lane, D35-compliant; digest delivers via Cloud API) and `waha-otp-handoff.json` (customer-facing Auth OTP via WAHA `sendText`, registry says inactive/nodes disabled). OTP is customer-facing/transactional and is outside the D35 exception: keep disabled, and consider deleting the draft + build script to remove the temptation. No WAHA container in infra/docker-compose.yml.
- Failure alerting: only reconciliation, payment-sweeper, release-job, payouts, dispatch/logistics and uptime workflows contain an inline error branch; the shared handler `money-workflow-error-alert.json` must be bound per workflow in the live instance (founder gate; cannot verify from repo). `unpaid-order-cancel.json`, `order-jobs.json`, `event-*`, `tickets-*` have no error page.
- Registry completeness test exists (tests/test_n8n_registry.py) so drift is caught for files, not for live state.

## Verified OK (no action)
HMAC verify before parse, 401 on missing signature, dup-ignore on 23505 (webhooks_lenco.py); Meta/WAHA/Cloudinary signature checks with compare_digest; webhook body replay safe via unique event_id; amount/currency/ref/provider-ref validation + hold; ordered locks in settlement; keyed ledger idempotency; customer + vendor notifications are written to the outbox inside the settlement txn (the unused `_emit_payment_success_notifications` helper in state.py:754 is dead code; harmless); money conversions only via Decimal; no PII in structured logs; frontend route paths all resolve to existing backend routes (only `/cart/rfq/{id}/accept` looked missing, it exists).

## Implementation batches (exclusive file ownership)

### Batch 1 — auto-mergeable (no payment/escrow/ledger files)
Agent 1A (catalog perf + follows): A:routers/catalog.py, A:services/listings/demo.py, NEW A:services/db_chunk.py, A:routers/follows.py, A:routers/products.py (images in_ only), A:routers/directory.py (images in_ only), related tests. Items H4, H5.
Agent 1B (rate limits): A:core/ratelimit_policies.py (new dependency), routers: cart.py, cart_tickets.py, account.py, account_birthday.py, kyc.py, kyc_media.py, media.py, listing_images.py, listing_import.py, vendor_orders.py, ticket_types.py, organiser_events.py, organiser_event_ops.py, order_confirmation.py, disputes.py, pickup_verify.py, checkout.py, checkout_extras.py, checkout_payment.py, consents.py, privacy.py, vendor_coupons.py, vendor_listings_manage.py, services_listings.py, ticket_wallet.py, rfq.py, clips_upload.py, event_team_accept.py, job_completion.py, admin_* (roles, governance_ops, coupons, business, translations, accounts, events, event_advance_debts-excluded: money), tests. Item H3 (non-payment part). NOTE: exclude orders_create.py, payment_status.py, payments_card.py, order_delivery.py (door payment), admin_event_advance_debts.py -> Batch 2.
Agent 1C (hygiene): A:logging.py, A:core/internal_token.py (+ `tokens_match`) and the 24 internal_* routers' compare line ONLY (mechanical; do not touch internal_payouts/internal_reconciliation/internal_payment_sweeper/internal_release_job/internal_event_release -> Batch 2), A:routers/internal_order_jobs.py 503-on-DB-failure (M4; it only lists/cancels unpaid order status via guarded transition, no ledger), tests. Items M3, M4, M5.

### Batch 2 — NEEDS-KING (payments/escrow/ledger; do not auto-merge)
Agent 2A (payment initiation + stuck states): A:services/payments/initiate.py, A:services/payments/reconcile.py (poll + drain backoff), A:services/payments/state.py (sweeper `initiated`, M1 fee booking, drain handling), A:routers/payment_status.py (validated payer number, operator derivation, rate limit), A:routers/orders_create.py + A:routers/payments_card.py + A:routers/order_delivery.py (rate limit only), a new migration only if `record_collection_failure` needs an initiated-path variant (additive, reversible). Items C1, H2, H3 (money part), M1, M2, M8.
Agent 2B (webhook ops + alerts): NEW infra/n8n/webhook-drain.json, NEW infra/n8n/door-poll.json, docs/ops/n8n-workflows.md (registry rows), docs/ops/n8n-activation-runbook.md, A:routers/internal_reconciliation.py, A:routers/webhooks_lenco.py (no behavior change), NEW internal tick + outbox template for late-collection alerts (A:services/payments/reconciliation_alerts.py, additive migration for a view), A:routers/internal_payouts.py/internal_release_job.py token compare, tests. Items C2, H1, M9 (OTP draft removal proposal is a separate founder call).

Founder checks (cannot be done from code): export the live n8n workflow list and confirm webhook-drain-tick (30s) and door-poll-tick are scheduled and that `settings.errorWorkflow` is bound on every money workflow; confirm Lenco dashboard webhook URL/secret; confirm `INTERNAL_*` tokens set in prod.
