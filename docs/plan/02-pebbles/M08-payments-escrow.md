# M08 — Payments & Escrow (Lenco) — Pebbles

12 pebbles. **Highest-risk mountain.** Contract source: `docs/ops/lenco/lenco-api-distilled.md` — every prompt references it. Invariants: integer ngwee internally, `Decimal` only at Lenco boundary; every handler idempotent (Lenco retries 30min × 24h); every money event = balanced ledger transaction; every endpoint authz + rate-limited; float on money = review-blocking.

---

### M08-P01 — Payment abstraction & money primitives `M`
**Deps:** M03-P05 · **Files:** `services/api/app/services/payments/base.py` (strategy interface: initiate_collection, query_status, initiate_payout, resolve_account, verify_webhook), `payments/registry.py`, `payments/money.py` (**ngwee↔decimal-major-string via `Decimal` only**, currency guard), `payments/references.py` (codec `ord-*`/`pay-*`/`rfd-*`, charset `[-._A-Za-z0-9]`, parse/generate), `services/api/tests/test_money.py`
Provider-agnostic seam (Lenco first; Flutterwave/PawaPay later per D11).
**AC:** float anywhere in money paths fails lint/custom AST check; codec round-trips; unknown-provider errors cleanly.
**Tests:** ngwee↔"1234.56" goldens (0, odd ngwee, max bigint), invalid charset rejected, no-float AST test.

### M08-P02 — Lenco API client `L`
**Deps:** P01 · **Files:** `services/api/app/services/payments/lenco/client.py`, `lenco/models.py` (typed contracts per distilled doc), `lenco/config.py` (sandbox/prod base URLs + token env names), `services/api/tests/test_lenco_client.py` (respx-mocked)
Collections (mobile-money USSD-push — **MTN/Airtel; Zamtel behind config flag pending F9a**), transaction status query, `/resolve` account-name, payouts (MoMo + bank), typed error taxonomy (declined/timeout/insufficient/invalid-number), timeouts + bounded retries on idempotent GETs only.
**AC:** every call typed both directions; amounts cross boundary as decimal-major strings via P01 converters; secrets from env only.
**Tests:** contract tests vs recorded sandbox fixtures; error taxonomy mapping; retry only on safe methods.

### M08-P03 — Webhook endpoint `L`
**Deps:** P02, M03-P05 · **Files:** `services/api/app/routers/webhooks_lenco.py`, `app/services/payments/webhook_verify.py` (HMAC-SHA512 over raw body, key = SHA256(api-token)), `services/api/tests/test_webhooks.py`
Signature verification on RAW body before parse; **idempotent ingestion** via `webhook_events.event_id` unique (dup → 200 no-op); out-of-order tolerance (status precedence rules); forged/invalid sig → 401 + alert log; processing enqueues domain handling (never inline heavy work); always fast-200 on valid+stored.
**AC:** duplicate, out-of-order, forged, and replayed webhooks each handled per spec (all tested); raw payload persisted for audit.
**Tests:** the four attack/edge cases + malformed JSON + unknown event type (stored, flagged, 200).

### M08-P04 — Payment state machine & orphan sweeper `L`
**Deps:** P03 · **Files:** `services/api/app/services/payments/state.py` (guarded transitions: created→ussd_pushed→pay_offline→success|failed|expired|cancelled + audit), `app/services/payments/initiate.py` (collection kickoff for an order/checkout_group), `app/routers/internal_payment_sweeper.py`, `infra/n8n/payment-sweeper.json`, `services/api/tests/test_payment_state.py`
USSD-push edge cases explicit: timeout, user-cancel, phone off → expiry sweeper marks stale `pay_offline` expired (after status re-query, not blindly) and releases the order for retry; illegal transitions raise; every transition audited.
**AC:** the mountain's biggest risk (orphaned states) closed: sweeper re-queries Lenco before expiring; success-after-expiry webhook handled (late-success reconciliation path documented + tested).
**Tests:** full transition table (legal/illegal); sweeper re-query behavior; late-success arrival.

### M08-P05 — Escrow ledger engine `L`
**Deps:** P01, M03-P05 · **Files:** `services/api/app/services/ledger/engine.py` (post_transaction API), `ledger/templates.py` (posting templates: charge_received, escrow_hold, commission_capture, release_to_vendor, payout_executed, refund_lane1/lane2, cod_collected, clawback), `services/api/tests/test_ledger.py` (incl. property tests)
Double-entry over M03-P05 tables; templates are the ONLY write path (no ad-hoc postings); each template documents debit/credit legs; idempotency key per business event.
**AC:** **property test: Σ postings = 0 for every generated transaction across random amounts/templates**; same event key posts once; account balances derivable + indexed.
**Tests:** hypothesis property tests; template goldens per money event; idempotent re-post.

### M08-P06 — Card via Lenco hosted widget `M`
**Deps:** P04 · **Files:** `services/api/app/routers/payments_card.py` (widget session create + callback + **server-side verify before fulfilment**), `apps/customer/app/[locale]/(shop)/checkout/card/[paymentId]/page.tsx` (widget embed/redirect + return handling)
NO direct card API (PCI). Verify = status query to Lenco on return AND webhook cross-check; fulfilment only after server-verified success; mismatch → hold + alert.
**AC:** spoofed success redirect without Lenco-verified status does NOT confirm order (tested); widget failure returns to payment step with retry.
**Tests:** forged-return test; verify-webhook race (either first) converges to single success handling.

### M08-P07 — Reconciliation poller & daily report `M`
**Deps:** P04, P05 · **Files:** `services/api/app/routers/internal_reconciliation.py` (30-min poll: re-query non-terminal payments; daily: Lenco balance/transactions vs ledger), `app/services/payments/reconcile.py`, `infra/n8n/reconciliation.json`, `services/api/tests/test_reconcile.py`
Mandatory per distilled doc: poller closes webhook gaps; daily report (ngwee-exact diff, orphaned Lenco txns, ledger-only txns) persisted + surfaced to M13 dashboard + founder digest.
**AC:** injected mismatch (fixture) flagged in report; poller state-machine-safe (uses P04 transitions, never raw updates); report matches sandbox to the ngwee.
**Tests:** gap-closing scenario (webhook lost → poller completes payment); mismatch detection; idempotent re-run.

### M08-P08 — Escrow release rules engine `L`
**Deps:** P05, M09-P01 · **Files:** `services/api/app/services/escrow/release.py` (rule evaluation: buyer-confirm / 48h-after-delivered auto / 7d-after-shipped fallback / dispute hold; event-escrow timing T+24h or 50/50 T-7/T+1 per D5 — consumed by M10-P08), `app/routers/internal_release_job.py`, `infra/n8n/release-job.json`, `services/api/tests/test_release.py`
Windows read from config; dispute opens → hold (release blocked until resolution); release posts ledger template + enqueues payout eligibility; job idempotent under re-run/overlap.
**AC:** each rule path produces exactly one release posting; dispute hold beats every timer; config window change respected without deploy.
**Tests:** timer matrix (confirm early, auto-48h, 7d fallback), dispute interleavings, double-run idempotency.

### M08-P09 — Payouts `L`
**Deps:** P05, P02, M03-P05 · **Files:** `services/api/app/services/payouts/` (eligibility from released balance, **pre-payout `/resolve` name-match** vs KYC momo name, execution, batching, retry/backoff, failure→alert), `app/routers/internal_payouts.py`, `services/api/tests/test_payouts.py`
KYC-tier velocity caps enforced (T1 limits from quotas config); name mismatch → payout held + vendor notified (never auto-sent); bank vs MoMo rails (instant vs 24–36h expectations recorded); every payout = ledger transaction; failures retried with cap then dead-lettered to admin queue.
**AC:** payout never exceeds vendor released balance (race-tested); mismatch blocks; retries never double-pay (idempotent reference).
**Tests:** balance race, resolve-mismatch, retry-after-timeout (status re-query before re-send), velocity cap boundary.

### M08-P10 — Refunds & clawbacks `L`
**Deps:** P05, P09 · **Files:** `services/api/app/services/refunds/` (lane-1 full incl. delivery; **lane-2 computed: item − outbound delivery − return transport − restocking fee (config 5–15%, default 10%)**; refunds-as-payouts to customer MoMo; post-release clawback ledger against vendor's future payouts), `app/routers/refunds.py` (admin/dispute-triggered), `services/api/tests/test_refunds.py`
No Lenco refunds API — refund = payout to customer + balancing postings; pre-release refunds from escrow; post-release create vendor clawback balance netted from next payouts.
**AC:** lane-2 math ngwee-exact per D17 in tests; clawback nets correctly across multiple future payouts; refund idempotent.
**Tests:** lane-2 fee matrix (min/max restocking config), pre vs post release paths, partial clawback across 3 payouts, double-execution guard.

### M08-P11 — COD lifecycle `M`
**Deps:** P05, M07-P06 · **Files:** `services/api/app/services/payments/cod.py` (order-time cod_receivable postings, delivery-collection confirmation → cash-collected postings, vendor-remit vs platform-collect reconciliation entries), `app/routers/cod.py` (admin/vendor confirm-collection endpoints), `services/api/tests/test_cod.py`
Cap ≤K500 re-enforced server-side at order creation (config); COD orders skip Lenco but flow the SAME ledger + commission pipeline; uncollected/refused delivery path (order cancelled, receivable reversed).
**AC:** COD commission captured on collection confirmation; refused-delivery reverses cleanly; cap tamper-proof.
**Tests:** collection confirm postings, refusal reversal, cap enforcement at API layer, commission math.

### M08-P12 — Commission engine & sequential invoicing `M`
**Deps:** P05, M03-P05/P07 · **Files:** `services/api/app/services/commissions/engine.py` (bps from snapshot — never live config post-purchase; supplies +3% stacking rule per CLAUDE.md), `app/services/invoicing/` (**gapless sequential numbering via invoice_counters FOR UPDATE**, tax-invoice/receipt payload builder, VAT-flag aware — off at launch, VSDC seam stub), `services/api/tests/test_commissions_invoicing.py`
Invoice issued on payment success (receipt) + order completion (tax invoice data), ZRA-ready fields; numbering gapless under concurrency.
**AC:** **concurrent invoice issuance produces gapless sequence (tested with parallel workers)**; commission uses purchase-time snapshot; VAT flag off yields compliant non-VAT invoice.
**Tests:** concurrency gapless test, commission matrix per D4 categories incl. free events 0%, snapshot immunity to config change.
