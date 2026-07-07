# Phase 2 — Waves (Vergeo5)

**Date:** 2026-07-06 · 141 pebbles across 19 waves (W0–W18). **Wave N is dispatched only after every Wave N−1 PR is merged.** Within a wave, every pebble maps to one Cursor cloud agent on its own branch/PR (`M{nn}-P{nn}: {title}`) with **exclusive file ownership** — verified below against each pebble's Files list.

## Shared-file conventions (what makes the waves conflict-free)

1. **No barrel files** in `packages/ui` — deep imports only; each component pebble owns its own files.
2. **FastAPI router auto-discovery** (M01-P02) — pebbles add router modules, nobody edits `main.py`.
3. **One migration file per pebble**, `NNNN_slug.sql`. Exact numbers for post-M03 migrations are assigned in each Phase 3 prompt (Claude allocates next-available per wave — no filename collisions).
4. **i18n messages are per-namespace files**; a namespace file is touched by at most one pebble per wave (collisions resolved by wave placement: e.g. `vendor.json` → M12-P11 W4, M12-P01 W6, M09-P02 W10).
5. Next.js routes are file-scoped by nature; the few cross-pebble file modifications (PDP buy-box, search zero-results, event ticket-picker stub, invoice link stub, `Caddyfile`, `ci.yml`, customer root layout) are explicitly sequenced into later waves than their owners — each is flagged in the pebble spec.
6. **Intra-wave interface edges** (marked ⚙ below): the dependent pebble codes against an already-merged contract (M03 table contracts or the M08-P01 strategy interface), stubbing the sibling service; the reviewer verifies integration in Phase 4. Used sparingly to keep M08/M09 from stretching into 4 extra waves.

## Wave table

### Wave 0 — Foundations (SEQUENTIAL — run one at a time, in order) · 7 pebbles
M01-P01 → M01-P02 → M01-P03 → M01-P04 → M01-P05 → M01-P06 → M01-P07
*Rationale:* every later pebble stands on repo, API skeleton, Supabase pipeline, app shells, CI, and deploy rails. No parallelism — each consumes the previous.

### Wave 1 — Tokens, i18n, first schema · 4 (parallel)
M02-P01 (tokens) · M02-P02 (i18n+formatK) · M03-P01 (identity/vendors schema) · M03-P07 (config tables)
*Edges:* all dep W0 only. Config tables (P07) FK-free of later schema; identity is the FK root for everything.

### Wave 2 — Component kit + core schema · 7
M02-P03 (forms) · M02-P04 (cards/price) · M02-P05 (overlays) · M02-P06 (nav) · M02-P08 (media UI) · M03-P02 (catalog schema) · M03-P03 (services/events schema)
*Edges:* M02-P03–P06 dep P01/P02 (W1); M03-P02/P03 FK vendors (W1). Two schema pebbles own separate migration files, FK targets all merged.

### Wave 3 — Orders schema, auth config, media backend · 5
M02-P07 (preview page) · M03-P04 (orders spine — FKs listings/tickets from W2) · M04-P01 (Supabase auth + SMS hook) · M05-P10 (Cloudinary signing + URL helper) · M15-P06 (legal pages — content-independent, starts early)
*Edges:* preview needs all W2 components; M15-P06 needs only i18n (W1) + footer file it owns.

### Wave 4 — Money/trust/search schema, API auth, guards · 6
M03-P05 (money schema — FK orders W3) · M03-P06 (trust/ops schema) · M03-P08 (search projection) · M04-P02 (API auth dependency) · M04-P03 (frontend auth clients/middleware) · M12-P11 (vendor pitch page — creates `vendor.json`)
*Edges:* three schema pebbles, disjoint migrations, FK targets merged. **Schema freeze after this wave — additive-only rule active.**

### Wave 5 — Schema proof, auth UI, admin shell · 5
M03-P09 (RLS matrix + seed framework) · M03-P10 (typegen + Pydantic base + catalog seed) · M04-P04 (auth UI) · M04-P07 (rate limiting + OTP guards) · M13-P01 (admin hardening/audit middleware — owns `Caddyfile` edit this wave)
*Edges:* P09/P10 validate the frozen schema; nothing downstream dispatches until the RLS matrix is green (gate within the gate).

### Wave 6 — First feature fan-out · 8
M04-P05 (account pages) · M04-P06 (DPA export/delete) · M05-P05 (search API) · M07-P01 (cart domain) · M12-P01 (onboarding UI) · M12-P02 (KYC backend + caps) · M13-P07 (config editors) · M14-P01 (outbox dispatcher)
*Edges:* all dep ≤W5. `vendor.json` touched only by M12-P01 this wave.

### Wave 7 — Customer surfaces + vendor listing core · 8
M05-P01 (home/merch slots) · M05-P02 (PLP) · M05-P03 (PDP) · M05-P06 (search UI) · M07-P02 (reservations — race-critical) · M12-P03 (listing create) · M12-P05 (image upload) · M13-P02 (KYC review queue)
*Edges:* home reads seeded merch config (W1); listing create dep caps (W6); ⚙ M12-P03↔P05 integrate via listing_images contract (M03-P02).

### Wave 8 — Discovery completion + checkout front half · 10
M05-P04 (comparison) · M05-P07 (supplies tab) · M05-P08 (directory) · M05-P11 (events browse) · M07-P03 (cart UI — modifies PDP buy-box, owner M05-P03 merged W7) · M07-P04 (checkout steps 1–2) · M12-P04 (listing manage) · M12-P06 (CSV import) · M12-P09 (storefront profile) · M13-P03 (canonical moderation)
*Edges:* all deps ≤W7. Largest wave — dispatch in two batches if Cursor capacity strains; no ordering constraint between them.

### Wave 9 — Payment seam + order state machine · 6
M05-P09 (SEO pass — needs all shop routes, W8) · M07-P05 (checkout steps 3–4) · M08-P01 (payment abstraction + money primitives) · M09-P01 (order state machine) · M13-P04 (flag queues) · M13-P08 (merch manager — home merged W7)
*Rationale:* the two money/state cornerstones (M08-P01, M09-P01) merge before the payment fan-out.

### Wave 10 — Lenco client, ledger, order creation · 8
M07-P06 (atomic order creation) · M08-P02 (Lenco client) · M08-P05 (ledger engine) · M09-P02 (vendor order actions — adds to `vendor.json`) · M13-P06 (order ops console) · M14-P02 (WhatsApp client/templates) · M14-P04 (SMS/email + fallback chain) · M16-P01 (perf budgets CI — **from here every wave is budget-policed per-PR**)
*Edges:* M07-P06 dep M09-P01+M07-P02; M08-P02/P05 dep P01. ⚙ M13-P06 escrow manual ops code against M08-P05 templates (same-wave: stub + Phase 4 verify).

### Wave 11 — Webhooks, payment states, invoicing · 8
M08-P03 (webhook endpoint) · M08-P04 (payment state machine + sweeper) · M08-P12 (commissions + gapless invoicing) · M09-P03 (pickup QR issuance/verify API) · M09-P05 (customer order pages — creates `orders.json`) · M12-P07 (vendor daily-driver) · M14-P03 (WA webhook + STOP) · M14-P05 (lifecycle event wiring)
*Edges:* ⚙ M08-P04 consumes P03's ingestion via the `webhook_events` table contract (merged M03-P05).

### Wave 12 — Payment completion fan-out · 9
M07-P07 (USSD wait UX) · M08-P06 (card widget) · M08-P07 (reconciliation) · M08-P08 (release rules) · M08-P09 (payouts) · M08-P10 (refunds/clawbacks) · M08-P11 (COD lifecycle) · M09-P04 (pickup scanner UI) · M09-P06 (confirm-received/report-problem)
*Edges:* all dep ≤W11. ⚙ M08-P10 executes payouts via the M08-P01 strategy interface (P09 sibling); ⚙ M09-P06 triggers release via M08-P08's declared interface. Reconciliation (P07) is the integration net for both.

### Wave 13 — Post-order + events/ticketing start · 8
M09-P07 (returns lane 1) · M09-P08 (returns lane 2) · M09-P09 (disputes — `orders.json` edit safe, owner M09-P05 merged W11) · M09-P10 (auto-confirm/release jobs + dispatch timeline) · M10-P01 (organiser event CRUD — adds organiser keys to `events.json`, owner M05-P11 merged W8) · M10-P02 (ticket types/inventory) · M12-P08 (payouts view) · M14-P06 (n8n workflows — creates `n8n-workflows.md` registry)
*Note:* M13-P05 (disputes console) deferred to W14 so M09-P09's dispute service merges first.

### Wave 14 — Ticket money path + services start · 9
M06-P01 (embedding pipeline) · M10-P03 (ticket purchase — replaces M05-P11 CTA stub) · M10-P04 (ticket wallet QR) · M10-P06 (verify API) · M11-P01 (service listings) · M11-P02 (post-a-job) · M13-P05 (disputes console — M09-P09 merged W13) · M13-P09 (dashboards — AI-usage tile renders "no data" until M06-P03/P06 land; flagged) · M14-P07 (template i18n)
*Edges:* ⚙ M10-P04↔P06 share the QR window algorithm — spec pinned in both prompts (HMAC/60s/±1), goldens shared via fixture file owned by P04.

### Wave 15 — AI core, scanner, quotes · 9
M06-P02 (RAG API) · M06-P03 (quotas/kill-switch) · M07-P08 (abandoned-checkout events) · M10-P05 (scanner PWA) · M10-P07 (transfer-to-friend) · M10-P08 (organiser dashboard + event escrow timing) · M11-P03 (quotes — creates `quotes.py`) · M13-P10 (support inbox-lite) · M15-P01 (reviews)
*Edges:* ⚙ M06-P03 wraps P02's endpoint via dependency (same wave, disjoint files, integration in P05 evals W16).

### Wave 16 — AI completion, services money, aggregates · 9
M06-P04 (Ask Vergeo UI — modifies zero-results, owner M05-P06 merged W7) · M06-P05 (eval set + CI — owns `ci.yml` edit this wave) · M06-P06 (query analytics) · M10-P09 (events SEO) · M11-P04 (accept→deposit/balance escrow) · M11-P06 (contact stripping — modifies `quotes.py`, owner merged W15) · M12-P10 (vendor analytics) · M13-P11 (n8n digest + registry finalization — `n8n-workflows.md` owner M14-P06 merged W13) · M15-P02 (review aggregation)

### Wave 17 — Hardening pass · 8
M11-P05 (job completion + review) · M15-P03 (headers/CSP — owns `Caddyfile` + all `next.config.ts` this wave) · M15-P04 (rate-limit sweep + fuzz) · M15-P05 (OWASP audit + authz matrix — owns `ci.yml` edit this wave) · M15-P07 (ZRA invoices/VSDC seam — replaces M09-P05 invoice stub) · M15-P08 (prohibited categories) · M16-P04 (content pages) · M16-P05 (analytics — owns customer root layout edit this wave)

### Wave 18 — Launch QA · 7
M15-P09 (restore drill/DR) · M16-P02 (PWA — consolidates M10 SW fragments) · M16-P03 (i18n completeness — edits `perf.yml`, owner M16-P01 merged W10) · M16-P06 (observability) · M16-P07 (E2E suite) · M16-P08 (k6 load test) · M16-P09 (beta tooling + go/no-go)
*Rationale:* everything exists; this wave proves it. Go/no-go checklist (M16-P09) closes Phase 2's build-out.

## Pebble count reconciliation
M01:7 M02:8 M03:10 M04:7 M05:11 M06:6 M07:8 M08:12 M09:10 M10:9 M11:6 M12:11 M13:11 M14:7 M15:9 M16:9 = **141** · Waves: 7+4+7+5+6+5+8+8+10+6+8+8+9+8+9+9+9+8+7 = **141** ✓

## Founder-gate overlay (from `00-decisions.md`)
- **F9a–f (Lenco answers)** wanted before Wave 10 dispatch (Lenco client); sandbox base URL/token (F9b) is hard-blocking for M08-P02 tests.
- **F5 (Meta/WhatsApp)** wanted before Wave 10 (M14-P02) for test-number E2E; mocks keep the pebble mergeable without it.
- **F8 (COD cap confirm)** before Wave 9 (M07-P05 encodes the gate).
- **F4 (counsel)** gates public real-money launch (W18 checklist item), not any build wave.
- **F1/F2 (domain/PACRA)** before W18 launch checklist sign-off.
