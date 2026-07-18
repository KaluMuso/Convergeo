# Analytics, Observability & Ethical Behavioural-Data — Implementation Plan

**Branch:** `claude/analytics-observability-plan-injyqj` · **Mode:** GATED (planning only — nothing implemented here) · **Next free migration:** `0056`
**Hard prerequisite for all three tasks:** **#267 / WP-1A** — the native psycopg3 transactional write adapter (`services/api/app/services/db.py`). It is **not yet on `origin/master`**; every analytics reader/writer reaches Postgres exclusively through its `run_sql_script`, so all work below merges **after** #267.

This document maps the current state (Part A), states the cross-cutting ethical-data requirements (Part B), and returns **three sequenced micro implementation tasks** (Part C), each sized for one Cursor/Claude session, with files, acceptance tests, privacy constraints, and dependencies. It does **not** implement anything.

---

## Part A — Current-state map (grounded, file:line)

### A0. The headline

Every analytics component — tables, writers, the client wrapper, admin/vendor dashboards, and the AI kill-switch — **already exists and is unit-tested**, but the **write path is dormant**: the writers have **zero production callers**. The single analytics row written in production today is `funnel_events(stage='abandoned')` (plus `ask_usage`, written by the Ask quota system). Everything downstream reads tables nothing populates. The work is therefore mostly **wiring and governance**, not green-field building.

### A1. Server event tables (all RLS: service-role write, admin read; anonymized by design)

| Table / view | Migration | PII columns | Written in prod today? |
| --- | --- | --- | --- |
| `funnel_events` | `0025_funnel_events.sql:7` | `customer_id`, `snapshot.customer_id` | **Partial** — only `stage='abandoned'` (abandon sweeper). Forward stages never written. |
| `search_query_log` | `0027_search_analytics.sql:10` | `term` (raw), `user_id` (30-day trim) | **No** — no live writer. |
| `analytics_events` + view `analytics_event_stream` | `0029_analytics_unify.sql:18,82` | `user_id`, `session_id` | **No** — no writer, no ingest, no consumer. |
| `ask_usage` / `ask_spend_monthly` | `0024_ask_usage.sql` | `user_id`, `guest_key`, `client_ip`, `question_hash` | **Yes** — Ask quota/spend system (`ask/quota.py:164`, `ask/spend.py`). |
| `ask_cache` | `0023_ask_cache.sql` | — | Yes. |

### A2. Writers (built, tested, mostly uncalled)

| Writer | Definition | Live caller? |
| --- | --- | --- |
| `funnel.record_event` | `analytics/funnel.py:122` | Only via `sweep_abandoned` (`funnel.py:277→286`). |
| `funnel.sweep_abandoned` | `analytics/funnel.py:277` | **Wired** — `routers/internal_funnel.py:36` (`POST /internal/funnel/abandon-tick`), n8n `infra/n8n/funnel-abandon.json` (5-min tick). |
| `emit_cart_add` / `emit_checkout_start` / `emit_step_complete` | `cart/events.py:10/25/40` | **None** — called only from `tests/test_funnel.py`. Docstring: "call from cart/checkout hooks *when wired*". |
| `emit_payment_start_funnel` / `emit_order_placed_funnel` | `orders/events.py:106/121` | **None** — tests only. |
| `search_log.log_search_query` / `log_ask_query` | `search_log.py:104/128` | **None** — never imported outside its module. |
| `events.record_event` (purpose-built for `product_view`/PDP) | `events.py:123` | **None**. |
| `events.query_funnel` (reads the union view) | `events.py:168` | **None**. |
| `search_log.trim_search_pii` (retention) | `search_log.py:153` | **None** — unscheduled (no endpoint, no n8n, no pg_cron, no GH-cron). |

All three writer modules reach the #267 spine via re-export: `funnel.py:13` (via `stock.claim`), `search_log.py:17` + `events.py:24` (via `orders.audit`).

### A3. Client wrapper `@vergeo/analytics` (scaffolded, inert)

- `track()` (`track.ts`) enqueues an **anonymized server beacon always** + mirrors to **GA4 only on consent**. Beacon → `NEXT_PUBLIC_ANALYTICS_ENDPOINT` default `/api/analytics/collect` (`track.ts:31`), payload `{events:[{event, props, ts}]}` (`track.ts:85-90`).
- `flush()` correctly wired to `visibilitychange`/`pagehide` in the provider (`analytics-provider.ts:63-64`), but the queue is **always empty**: `track()` is **called by zero app code** — all 6 typed events (`events.ts:13-48`) are dead (fired only in `track.test.ts`).
- Provider mounted **customer only** (`apps/customer/app/[locale]/layout.tsx:140`); GA4 script injection is real but **double-gated on env + consent** (`analytics-provider.ts:55`).
- **No consent UI** — `setAnalyticsConsent` is never called anywhere, so `vg_analytics_consent` stays `unset` and GA4 can never fire.
- **No client identity** — the beacon carries no `session_id`/`user_id`/anon-id (`track.ts:20-24,61`).
- **No server ingest** — no `/api/analytics/collect` router in the API and no `apps/*/app/api/analytics/collect/route.ts`; no proxy rewrite. The beacon POSTs into a 404.
- Vendor & admin apps don't depend on the package at all (dead GA4 CSP allowance in `apps/vendor/next.config.ts:25-28`).

### A4. Dashboards reading unwritten tables

| Surface | Endpoint | Reads | Status |
| --- | --- | --- | --- |
| **Vendor "Views / Cart activity" + Conversion** | `vendor_analytics.py:153` (`_views_by_day`, filter `:173` on `cart_add`/`checkout_start`); `:236` conversion | `funnel_events` forward stages | 🔴 **Always zero** — sits beside real Sales/Orders/Top-listings. |
| **Admin Search Insights** (top-terms, zero-results, ask-cost) | `admin_search_insights.py:41/56/71` | `search_query_log` | 🔴 **Always `[]`** — no live writer. (No admin UI consumes these yet — latent.) |
| **Admin AI-usage tile** | `admin_dashboards.py:21,295` | hardcoded `AI_USAGE_DATA_AVAILABLE=False`; never reads `ask_spend_monthly` | 🟡 **Inverse gap** — honest "no data" placeholder while spend *is* tracked. |
| **Unified `analytics_events` stream** | `events.query_funnel` / `analytics_event_stream` | `analytics_events` | 🔴 **Fully inert** — no writer, no reader. |

**Explicitly NOT gaps (real data):** admin GMV, orders-by-status, payout liabilities, reconciliation, catalog counts, and the admin **Funnel tile** (derived from `checkout_groups`+`orders`, not `funnel_events`, at `admin_dashboards.py:252`); vendor Sales/Orders/Top-listings (from `orders`/`order_items`); event-organiser stats (from `tickets`).

### A5. Observability (largely built, founder-gated)

- **Sentry** — API `core/sentry.py:117` (init at `settings.py:94-96`, PII scrubber, DSN-gated no-op); all 3 web apps have `sentry.client.config.ts` + `app/sentry-init.tsx` loaders mounted in every layout (customer `:137`, vendor `:54`, admin `:92`). **Gap:** no `instrumentation.ts`/`sentry.server.config.ts` → SSR/RSC/route-handler errors uncaptured (worst for customer SSR).
- **Structured logging** — `logging.py:12-32` (`JsonFormatter`, no-PII whitelist), `middleware.py:12-24` (`X-Request-ID` correlation, echoed). API-only; frontends have none.
- **Uptime** — `infra/uptimerobot.md` + n8n `uptime-alert.json` (`active:false`), founder-gated. **Gap A:** monitors/doc hit `/health` but API serves only `/healthz`/`/readyz` and Caddy (`infra/Caddyfile:57-60`) has no rewrite → keyword monitor reads a 404 as perpetual down. **Gap B:** neither health endpoint touches the `run_sql_script` DB spine (no deep liveness).
- **AI spend** — the **$15/mo kill-switch is fully built and enforced** (`spend.py:16` cap, `raise_if_killed` `spend.py:171` called in `quota.py:251`; guest-3/free-25 quotas). **Gaps:** (a) spend is not surfaced — dashboard tile is a placeholder, `/admin/search-insights/ask-cost` reads the empty `search_query_log`, and `ask_spend_monthly.total`/`killed_at` are exposed by no endpoint; (b) no warn/page as spend nears the cap (`killed` flag discarded, no n8n); (c) `reset_kill_switch` (`spend.py:157`) has no admin route.

### A6. Ethical-data posture (existing)

- **Anonymization by design** — `events.record_event` rejects raw-PII prop keys and non-integer money (`events.py` `_assert_anonymized`, `_PII_KEYS`); `search_query_log` stores `normalized_term`; the union view projects `normalized_term` only.
- **Consent boundary (documented, `docs/ops/analytics-events.md`)** — server operational log is written **regardless of consent**; consent gates **GA4 only**.
- **DPA** — `trim_search_pii` NULLs `user_id` after 30 days; `docs/ops/data-retention.md` covers user-initiated export/delete (`privacy.py`) but is **silent on analytics/event-table retention**.
- **Retention gaps** — `trim_search_pii` is **unscheduled**; `funnel_events` (the one table receiving PII today), `analytics_events`, `ask_usage`, and `notification_outbox` (raw `phone_e164` in payload) have **no sweeper at all**.
- **Identity stitching** — **absent**. No anon-session→user linkage; `analytics_events.session_id` is never populated; the only cross-phase link is `checkout_group_id`.

---

## Part B — Cross-cutting requirements (bind every task)

1. **Consent boundary (the ethical spine).** Server-side operational/analytics events are a **legitimate-interest operational record** → written **regardless of consent**, always anonymized. **GA4 (client) is convenience** → fires **only on explicit `granted`**. No task may gate a server event on consent, and none may fire GA4 without it.
2. **PII minimisation.** No raw PII in any analytics table. Search → `normalized_term` only into the unified stream. Money → integer ngwee (reject float/bool). The ingest endpoint (untrusted client) must re-assert `_assert_anonymized` server-side. Identifiers, not PII, in logs.
3. **Retention.** Any column that links an event to a person (`user_id`, `session_id`, `customer_id`, `guest_key`, raw `phone`) must have a documented window and a **scheduled** sweeper. Anonymized aggregates may be kept indefinitely.
4. **Fire-and-forget.** Analytics writes must **never** break the request that triggers them (swallow errors, as the existing writers already do).
5. **Identity is opaque.** Any session identifier is a random, expiring, first-party token — never a device fingerprint, never PII.
6. **House rules.** RLS on every new table; service-role writes; router **auto-discovery** (add a module exposing `router`, never edit `main.py`); one migration per pebble, additive + reversible; `uv run pytest`/`ruff`/`mypy` + `pnpm test`/`lint`/`typecheck` green; conventional commits, PR titled `M{nn}-P{nn}`.

---

## Part C — The three sequenced micro-tasks

```
#267/WP-1A (psycopg spine, must land first)
        │
        ▼
   ┌─────────────────────────────┐
   │ TASK 1 — Activate the spine  │  backend only, no schema
   └─────────────────────────────┘
        │            │
        ▼            ▼
 ┌──────────────┐  ┌──────────────────────────────┐
 │ TASK 2 —     │  │ TASK 3 — Governance:          │
 │ Client loop  │  │ retention + AI-spend + health │   (disjoint files → TASK 2 ∥ TASK 3)
 └──────────────┘  └──────────────────────────────┘
```

---

### TASK 1 — Activate the server-side event spine (wire the dormant writers)

**Goal.** Connect the already-built writers to their live request paths so the funnel, search, and Ask streams start recording — turning the empty vendor/admin dashboards into real data. Pure fire-and-forget calls at identified handlers; **no schema, no new modules, no new logic.**

**Dependencies.** #267/WP-1A. This is the foundation for Tasks 2 & 3.

**Files (modify only):**
- Funnel wiring (call the existing `emit_*` wrappers):
  - `services/api/app/routers/cart.py` (`add_cart_item`, ~`:365`) → `emit_cart_add`
  - `services/api/app/routers/checkout.py` (`create_checkout_session` ~`:429`; step validators ~`:587`, `:624`) → `emit_checkout_start`, `emit_step_complete`
  - `services/api/app/routers/checkout_payment.py` (`validate_payment_method` ~`:218`), `routers/payments_card.py` (`create_card_session` ~`:544`), `routers/payment_status.py` (`retry_payment` ~`:404`) → `emit_payment_start_funnel`
  - `services/api/app/routers/orders_create.py` (`create_orders` ~`:148`) → `emit_order_placed_funnel`
- Search/Ask logging:
  - `services/api/app/services/search/__init__.py` (`run_search` ~`:139`) → `log_search_query(normalized_term, zero_result, entity_counts)`
  - `services/api/app/services/ask/…` / `routers/ask.py` (`run_ask` where `model`/`total_tokens` are in hand ~`ask.py:243`) → `log_ask_query(usd_micros=…, zero_result=…)`
- Tests: extend `tests/test_funnel.py`, `tests/test_search_analytics.py`; add router-level assertions.

**Required changes.**
1. At each handler, add a single fire-and-forget emit/log call **after** the state change succeeds (so an event never precedes its fact). Reuse the `emit_*` wrappers verbatim — they already carry the correct snapshot/anonymization shape.
2. `log_ask_query` must pass the real `usd_micros` (derive from `model` + `total_tokens` already computed in `run_ask`) — this is the **only** data source for the per-day Ask-cost breakdown and it is currently discarded.
3. Search zero-result: pass `zero_result = (result total == 0)` from the `SearchResponse` — this feeds admin zero-result mining.
4. No behavioural change to any request on writer failure (swallow, log at debug — matching existing writers).

**Acceptance tests.**
- Real-Postgres (skip-if-unreachable): a `/search` request writes one `search_query_log` row with `normalized_term` (never raw PII beyond the existing `term` column) and correct `zero_result`; an Ask request writes a `kind='ask'` row with non-zero `usd_micros`; add-to-cart / checkout-create / step / payment-start / order-create each write the matching `funnel_events` stage (idempotent per `(checkout_group_id, stage)`).
- Downstream proof: after seeding via the handlers, `vendor_analytics._views_by_day` returns non-zero; `admin_search_insights.top_terms`/`zero_result_terms`/`ask_cost_by_day` return rows.
- **Failure-path:** patch `run_sql_script` to raise → the search/checkout/order request still returns 2xx (analytics failure is invisible to the user).
- `uv run pytest` + `ruff` + `mypy` green.

**Privacy constraints.**
- These are **server operational events → written regardless of consent** (no GA/consent gate here). State this in the PR.
- Anonymized: only `normalized_term` reaches insight surfaces; funnel snapshots already exclude PII; money integer ngwee; service-role writes.
- No new PII columns; no raw query text into `analytics_events`.

**Out of scope / seam.** No client work, no ingest endpoint, no `analytics_events`/`product_view` (that's Task 2). If a single session proves too large, split at the clean seam **{funnel wiring} | {search+ask logging}** — but they share no files, so one session is realistic.

**Status — ✅ SHIPPED (backend-only, no migration).** Wired the dormant writers into their live paths: search (`run_search` → `log_search_query` with per-entity counts + `zero_result` + best-effort `user_id`), Ask (`run_ask` → `log_ask_query` at all three resolution points — cached/refusal/answered — with `usd_micros` derived via the kill-switch's own `tokens_to_usd_micros`, so the log agrees with `ask_spend_monthly`), and funnel `cart_add` (`cart.py`), `checkout_start` (`checkout.py`), `payment_start` (`checkout_payment.py::validate_payment_method` — the common method-selection step every rail passes through), `order_placed` (`orders_create.py`). A new `record_event_best_effort` primitive next to `record_event` makes every funnel emit fire-and-forget, so an analytics write can never break a cart/checkout/payment/order request. Tests: `tests/test_analytics_wiring.py` (12 DB-free unit tests — call wiring + fire-and-forget); DB round-trips stay covered by `test_search_analytics.py` / `test_funnel.py`. **Deferred (no live consumer):** `step_complete` (intermediate contact/fulfilment steps) — its only reader `query_funnel` is unmounted and the checkout funnel step is already populated by `checkout_start` + `payment_start`; `payment_start` intentionally lives only at method-selection, not the card/retry execution paths.

---

### TASK 2 — Close the client loop: beacon ingest + identity + consent

**Goal.** Consume the client beacon, give it a stable **anonymous** identity, capture consent, and record the `product_view`/PDP step — completing the funnel Task 1 started and making the documented "server-always / GA-on-consent" boundary real end-to-end.

**Dependencies.** #267 + **Task 1** (shared analytics conventions and a non-empty stream; reuses `events.record_event`). Disjoint from Task 3 → may run in parallel with it.

**Files:**
- API (new, auto-discovered): `services/api/app/routers/analytics_collect.py` — `POST /analytics/collect`.
- Client: `packages/analytics/src/session.ts` (new — opaque session id) + edits to `track.ts` (attach id) / `analytics-provider.ts`; `apps/customer/app/[locale]/product/[slug]/…` PDP → `track('product_view', …)`.
- Consent UI (new): `apps/customer/app/[locale]/_components/ConsentBanner.tsx` (calls `setAnalyticsConsent`), mounted in the customer layout.
- Next transport: a rewrite in `apps/customer/next.config.ts` (or set `NEXT_PUBLIC_ANALYTICS_ENDPOINT`) so `/api/analytics/collect` reaches the FastAPI origin.
- Tests: `services/api/tests/test_analytics_collect.py`; `packages/analytics/src/session.test.ts` + consent/track vitest.
- **Migration:** none (`analytics_events.session_id` already exists).

**Required changes.**
1. **Ingest endpoint** — parse `{events:[{event, props, ts}]}`; enforce a **batch cap** (≤20 events, bounded body size → 413) and **rate-limit** (public, unauthenticated); map each event → `events.record_event`, attaching `session_id` (client) and `user_id` (from the bearer token **iff** present); re-run `_assert_anonymized` server-side (the client is untrusted) — reject/scrub PII keys and non-integer money; **fire-and-forget semantics** (a bad event never 500s the batch — skip and continue). Never trust client `ts` for ordering security; store as a prop.
2. **Client session id** — generate a random UUID stored in a first-party, `SameSite=Lax`, expiring cookie/localStorage (e.g. 180-day rolling); attach it to the beacon wrapper (`{session_id, events:[…]}`); **not** a fingerprint, **not** derived from any PII.
3. **`product_view`** — fire `track('product_view', { product_id, listing_id? })` on PDP mount.
4. **Consent banner** — minimal, i18n-keyed, calls `setAnalyticsConsent('granted'|'denied')`; governs the **GA4 mirror only** — the server beacon keeps flowing either way. Default `unset` = GA4 off.
5. **Server-side stitch (best-effort, forward-only)** — populate `analytics_events.session_id` + `user_id`; once a session authenticates, subsequent events carry `user_id`. **No historical backfill, no new table** (a full anon→auth backfill is explicitly deferred).

**Acceptance tests.**
- Ingest: valid batch → N `analytics_events` rows with `session_id`; a PII prop (`phone`/`email`) → rejected/scrubbed, not stored; a `*_ngwee` float → rejected; oversized batch → 413; over-rate → 429; malformed event → skipped, rest of batch still written; authed request stamps `user_id`, anonymous stamps only `session_id`.
- Client (vitest): `session.ts` returns a stable id across calls and attaches it to the beacon; consent banner writes the cookie and flips `hasAnalyticsConsent()`; GA4 mirror fires only after `granted`; server beacon enqueues regardless of consent.
- E2E: a PDP visit produces a `product_view` row reachable via `analytics_event_stream`.

**Privacy constraints.**
- **Defense-in-depth anonymization** at the ingest boundary (client cannot be trusted to pre-sanitise).
- Session id is opaque/random/expiring/first-party; it is a **person-linked identifier** → covered by the retention sweeper in Task 3.
- Consent governs GA4 **only**; the server beacon is operational and always anonymized. Rate-limit + size-cap protect the public endpoint.
- RLS unchanged: `analytics_events` stays service-role-write / admin-read; stitched `user_id` never exposes one user's events to another.

**Contingency (the set stays at three).** Task 2 ships as **one** session by default. Split into **2a {API ingest + server-side stitch}** and **2b {client session-id + consent banner + `product_view`}** — a clean, file-disjoint seam (2a is the critical path; 2b follows) — **only if** the single session overruns on file count or review size. This is a fallback, not the plan: the default remains three tasks.

**Out of scope.** GA4 SSR capture; vendor/admin client tracking; historical identity backfill; promo/affiliate attribution.

**Status — 🟡 SPLIT INVOKED (2a shipped, 2b next).** The session overran (Task 1 + this backend in one run) and the client transport carries real cross-origin subtlety — the customer app calls the API on an absolute `NEXT_PUBLIC_API_BASE_URL` (no `/api` proxy), so a `sendBeacon` needs either a Next rewrite or a `text/plain`+CORS beacon — so the documented 2a|2b split is used.

- **✅ 2a — server ingest (SHIPPED):** `services/api/app/routers/analytics_collect.py` → `POST /analytics/collect` (auto-discovered). Lenient batch parse (`extra="ignore"` so version skew never drops a batch), ≤20-event cap → 413, per-IP **fail-open** rate-limit (registered as `PUBLIC_BEACON` in `ratelimit_policies.py`), per-event props size bound, and a **persist allowlist** (`{product_view}`) so funnel/search events already recorded server-side (Task 1) are accepted-but-not-double-counted. Reuses `events.record_event` for server-side anonymization (rejects raw-PII / non-int money). **Forward identity stitch lives here:** a beacon carrying `session_id` + a bearer token writes both columns, linking `session_id` ↔ `user_id` (no historical backfill, no new table). Tests: `tests/test_analytics_collect.py` (10).
- **⏳ 2b — client loop (NEXT):** opaque client `session_id` (`packages/analytics/src/session.ts`) attached to the beacon; consent-capture banner (`setAnalyticsConsent`, mounted in the customer layout); `product_view`/PDP `track()`; transport (Next rewrite or `text/plain`+CORS); client vitest.

---

### TASK 3 — Governance: retention sweeper + AI-spend visibility + health-path fix

**Goal.** Make the PII-retention promise real and scheduled, surface AI spend and the kill-switch to the admin, and fix the false-down health path. Backend + infra + a small admin tile; disjoint from Task 2.

**Dependencies.** #267 + **Task 1** (retention is only meaningful once writers are live; the AI-spend tile reads `ask_spend_monthly`, which is **already** live, so that half is independent). Runs in parallel with Task 2.

**Files:**
- Retention: `services/api/app/services/analytics/retention.py` (new — unified sweep, generalising `trim_search_pii`); `services/api/app/routers/internal_analytics.py` (new — `POST /internal/analytics/retention-tick`, token-guarded like `internal_funnel.py`); `infra/n8n/analytics-retention.json` (new — daily tick); `docs/ops/data-retention.md` (add the analytics-tables section).
- AI-spend: `services/api/app/routers/admin_dashboards.py` (replace the `AI_USAGE_DATA_AVAILABLE=False` placeholder → read `ask_spend_monthly.total_usd_micros` + `killed_at`); `services/api/app/routers/admin_config.py` (or a small `admin_ai_spend.py`) — admin **kill-switch reset** endpoint calling `reset_kill_switch` (`spend.py:157`), admin-gated + audited; optional near-cap **warn** (n8n `ai-spend-warn.json` or in the `finalize_ask_answer` path at ≥80%).
- Health: `services/api/app/routers/health.py` — add a public `/health` alias (or repoint monitors to `/healthz` in `infra/uptimerobot.md`); optional deep `/readyz` that runs `SELECT 1` through the `run_sql_script` spine.
- Tests: `services/api/tests/test_analytics_retention.py`, `tests/test_admin_ai_spend.py`, `tests/test_health.py`.
- **Migration:** none required (operates on existing tables). `0056` available if a retention-run audit row or a `notification_outbox` purge index is wanted.

**Required changes.**
1. **Unified retention sweep** — one idempotent, service-role function that, past each window: NULLs `search_query_log.user_id` (existing 30-day rule), NULLs `funnel_events.customer_id` + strips `snapshot.customer_id`, NULLs `analytics_events.user_id` + `session_id`, and ages/purges delivered `notification_outbox` rows carrying raw `phone_e164`. Keep anonymized aggregates. Expose via the token-guarded internal tick; schedule daily in n8n (mirroring `funnel-abandon.json`).
2. **AI-spend tile** — surface real `total_usd_micros` vs `cap` and `killed_at` (aggregate only — **never** per-user question text); after Task 1, `ask_cost_by_day` gives the per-day breakdown.
3. **Kill-switch reset** — admin-only endpoint clearing `killed_at` via `reset_kill_switch`, written to the audit log; optional ≥80% warn to the founder (n8n).
4. **Health** — resolve the `/health` 404 so the uptime keyword monitor stops reading perpetual-down; optionally make readiness exercise the DB spine.

**Acceptance tests.**
- Retention: rows older than each window have their person-links NULLed/stripped; rows inside the window are untouched; aggregates survive; the sweep is idempotent (second run is a no-op); `notification_outbox` phone aged out. Internal tick rejects a missing/invalid token.
- AI-spend: the admin tile returns real spent/cap/`killed`; reset endpoint clears `killed_at`, writes an audit row, and is rejected for non-admins.
- Health: unauthenticated `GET /health` returns 200 with the "ok" keyword; deep `/readyz` fails when the DB spine is down (if implemented).
- `uv run pytest` + `ruff` + `mypy` green; migration (if added) replays clean.

**Privacy constraints.**
- Windows DPA-aligned (30-day person-link window for `user_id`/`session_id`/`customer_id`; longer only for tax-bound records, which live outside these tables). Sweeper idempotent + service-role.
- AI-spend surfaces **aggregate money only** — no question content, no per-user drill-down.
- Kill-switch reset audited (who/when); admin-gated.

**Out of scope.** SSR/RSC Sentry capture (a separate observability pebble); UptimeRobot/GA4/Sentry-DSN activation (founder config, not code); SMS/WhatsApp deliverability analytics.

---

## Part D — Sequencing, deferrals, and founder gates

**Order:** #267/WP-1A → **Task 1** → { **Task 2** ∥ **Task 3** }. One pebble = one branch = one PR. The set is **three tasks by decision**; Task 2 splits into 2a/2b only if a session overruns (see Task 2 → *Contingency*).

**Which dashboards come alive, and when:**
- After **Task 1**: vendor Views/Conversion; admin Search-Insights (top-terms, zero-results, ask-cost breakdown); funnel forward stages.
- After **Task 2**: `product_view`/PDP + unified `analytics_events` stream; consent-gated GA4 actually fires.
- After **Task 3**: admin AI-spend tile + kill-switch state; retention runs on a schedule; health monitors read true state.

**Explicitly deferred (not in these three):** full anon→auth historical identity backfill; SSR/RSC Sentry instrumentation; promo/affiliate/near-me attribution analytics; vendor/admin client-side tracking; per-user AI drill-downs. **Founder-gated config (no code):** Sentry DSNs, UptimeRobot account + `ops_uptime_alert` template (F5), `NEXT_PUBLIC_GA4_MEASUREMENT_ID`.

**One-line dependency statement for the PRs:** *every analytics reader/writer reaches Postgres only through `run_sql_script` (the #267 `db.py` psycopg3 spine), so this work must merge after #267/WP-1A lands on `master`.*
