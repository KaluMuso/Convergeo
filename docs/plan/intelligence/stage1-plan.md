# Convergeo Intelligence & Decision Engine — Stage 1 refined implementation plan

**Status:** Phase A deliverable (refined plan per the founder's refinements, §7). Stage 1A is delivered as the stacked `feat/intel-1a-*` branches listed in §1A.2; nothing is enabled anywhere.
**Base:** `origin/staging` @ `9d4f881e` (2026-11-12) · **Pilot launch:** 13 Nov 2026 · **Mode:** GATED, `analytics_v2` family default **OFF**
**Scope rule:** extend and consolidate what exists. No new infrastructure (no Redis requirement, no queue service, no warehouse, no new AI vendor). No change to checkout, payment or order semantics.

> Reading guide: §0 is the re-verified baseline (every claim checked against the code at the base SHA). §R answers refinements A–I one by one. §F is the `analytics_v2` flag, rollback, monitoring and compatibility contract shared by all three releases. §1A, §1B and §1C each give files and DB objects, PRs and dependencies, migration and rollback, performance and security, tests and acceptance, and open decisions. Every work item is tagged **[E] essential** or **[P] postponable**.

---

## 0. Re-verified baseline (what exists at `9d4f881e`)

| #   | Prior-assessment claim                                                                                        | Verified?                 | Evidence and corrections                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| --- | ------------------------------------------------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | `@vergeo/analytics` has a typed `track()` with a sendBeacon queue that flushes only on hide or at 20 events   | ✅                        | `packages/analytics/src/track.ts` (`MAX_BATCH = 20`, `flush()` only from `analytics-provider.ts` on `visibilitychange` and `pagehide`). There is no time-based flush, so a long visible tab holds events until hide. If `sendBeacon` returns false the batch is lost (the queue is cleared before sending).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2   | `POST /analytics/collect` persists only `product_view`, one INSERT per event, sync DB calls in an `async def` | ✅                        | `routers/analytics_collect.py`: `SERVER_PERSIST_EVENTS = {"product_view"}`; it loops `record_event()`, which calls `run_sql_script()` (psycopg **sync** pool, `services/db.py`) directly inside `async def collect`. Each call **blocks that worker's event loop** for the INSERT. If the pool (max 5) is exhausted it blocks for up to `SUPABASE_DB_POOL_TIMEOUT=10s`, stalling every request on that worker, checkout included.                                                                                                                                                                                                                                                                                                                                                          |
| 3   | The rate limit writes a DB row per beacon                                                                     | ✅                        | `bump_rate_counter()` makes a PostgREST RPC (an HTTP round trip plus an UPSERT on `rate_counters`) **per beacon** in `analytics_collect` and `telemetry_views`. It runs before the body is processed. It fails open.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 4   | `get_client_ip` trusts the leftmost XFF                                                                       | ✅, **with a correction** | `core/ratelimit.py::get_client_ip` takes `XFF.split(",")[0]`. In production, Caddy 2.9 (`infra/Caddyfile`, no `trusted_proxies`) **replaces** an untrusted incoming XFF with its TCP peer. `api.vergeo5.com` is orange-clouded (`infra/cloudflare-dns.md`), so that peer is a **Cloudflare edge IP**, not the visitor. Beacons also arrive through the **Vercel rewrite** (`apps/customer/next.config.ts` → `/api/analytics/collect`), so Cloudflare's `CF-Connecting-IP` is a **Vercel egress IP**. Net effect: the key is not visitor-spoofable through the normal path, but it is **shared by many unrelated visitors** (CF or Vercel IPs), so per-IP limits throttle the wrong population. Anyone who reaches the origin directly (no origin lock is documented) can forge any header. |
| 5   | `analytics_events` (0029): admin-read RLS; person links NULLed at 30d; rows never deleted                     | ✅                        | `0029_analytics_unify.sql` (RLS + FORCE, admin select, service_role all). `services/analytics/retention.py` runs an `UPDATE … SET user_id=NULL, session_id=NULL`. That rewrites every row once at 30 d (MVCC bloat), and the rows themselves live forever.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 6   | `funnel_events` (0025) is server-side, idempotent per group/stage, no anon id                                 | ✅                        | Unique `(checkout_group_id, stage) WHERE checkout_group_id IS NOT NULL`. `cart_add` is emitted with `checkout_group_id=None` (`routers/cart.py:767`), so cart adds are **not** idempotent and have no session or anon link. All emits run **synchronously in async handlers** (`cart.py`, `checkout.py:708`, `checkout_payment.py:240`, `orders_create.py:331`). This is the same event-loop-blocking issue as #2, but **on the transactional path**.                                                                                                                                                                                                                                                                                                                                      |
| 7   | `search_query_log` (0027) keeps the raw term forever                                                          | ✅, **worse**             | The `term` column is NOT NULL and never scrubbed. `admin_search_insights.py` returns `min(term) AS sample_term`, so a raw query (which could contain a phone number or a name) reaches the admin UI. The row is never deleted. Only `user_id` is trimmed at 30 d.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 8   | `listing_analytics` + `listing_view_dedup`: `surface` never sent; dedup never purged                          | ✅                        | `listing_views._record_one` calls the 4-arg form, so `surface` defaults to `'unknown'` (`20260813160100…`). `listing_view_dedup` has **no purge anywhere**. With ~33 impressions per session it is the **largest unbounded growth** in the analytics schema (see §R-G).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 9   | `vg_session_id` never rotates; beacons can't carry the Bearer token, so the user stitch fails                 | ✅                        | `session.ts` keeps one localStorage UUID forever. It is a visitor id, not a session. `track.ts` uses `sendBeacon` (no headers), so `_optional_user_id` in collect is always `None` for real browsers.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 10  | The GA4 mirror's consent is never set, so GA4 never loads                                                     | ✅                        | `setAnalyticsConsent` has **zero** callers in `apps/`. The cookie stays `unset` and `AnalyticsProvider` never injects gtag.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 11  | `retention.py` sweep plus n8n tick                                                                            | ✅                        | `POST /internal/analytics/retention-tick` ← `infra/n8n/analytics-retention.json` (daily 03:00; the workflow already pins `settings.timezone = "UTC"` — `docs/ops/data-retention.md` said otherwise and is corrected in 1A-07).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 12  | Admin `DashboardBoard.tsx`; the funnel query scans all rows; `admin_search_insights.py` has no UI             | ✅, **plus a bug**        | `admin_dashboards._funnel_snapshot` and `_orders_by_status` `select("status")` over **all** `checkout_groups` and `orders` through PostgREST. Supabase's default `max_rows=1000` **silently truncates** these counts once there are more than 1,000 rows, so the funnel and status tiles will under-report after launch. `compute_gmv_ngwee()` is correct: it is a SQL aggregate over authoritative `orders`/`order_items`.                                                                                                                                                                                                                                                                                                                                                                |
| 13  | API: 2 uvicorn workers × pool 5                                                                               | ✅                        | `infra/api.Dockerfile` (`--workers 2`), `services/db.py` (`SUPABASE_DB_POOL_MAX` default 5) → up to 10 direct connections plus PostgREST traffic.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 14  | No orders or payments yet; pilot 13 Nov 2026                                                                  | ✅ (per brief)            | Nothing in the repo contradicts it. Every money metric therefore starts at zero and must come from authoritative tables (§R-I).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

**Additional findings that shape the plan:**

- `search_log.log_search_query` is called inline in `services/search/__init__.py:550` (sync, request path).
- `telemetry_views` already uses `BackgroundTasks`, which is the right pattern but is still per-beacon DB rate-limited.
- An optional Upstash Redis REST config already exists (`settings.upstash_redis_rest_url`, `ttl_cache.py`, `listing_views._UpstashDedupStore`). It is **not** used by this plan: it would add an external hop to every beacon, and it is unset in production.
- n8n already runs `admin-digest.json` (06:00 UTC founder WhatsApp digest via `/internal/digest`) and `daily-summary.json`. 1C extends these instead of adding a parallel digest.
- The privacy policy (`packages/i18n/messages/*/legal.json` §cookies) already says "Analytics (e.g. GA4) may be used with consent where required", so removing GA4 needs a copy change.

---

## R. Technical refinements A–I

### R-A. Estimated versus actual session end — [E]

- **Rule:** a v2 session is a run of events from one browser with no gap above **30 minutes** of inactivity. The client rotates `session_id` when `now − last_activity > 30 min` (`packages/analytics/src/v2/ids.ts`). Rotation emits a `session_start` with `entry_page_key` and a coarse `referrer_kind` (`direct|search|social|internal|other`; never the URL).
- **We never emit "session_end" and never claim an exit time.** Rollups (1B) derive `session_last_seen_at = max(client_ts)` and report **`estimated_session_end = last_seen_at`**, flagged `end_kind = 'inactivity_estimated'`. Duration is reported as `last_seen − first_seen`, named _active span_, not "time on site". A single-event session has an active span of 0 and is counted as a **bounce**.
- `pagehide` and `visibilitychange` remain **flush triggers only**. They are not recorded as exits: mobile browsers fire them on app-switch, so they would overstate exits on 3G and Android.
- Admin UI copy uses the i18n keys `analytics.session.estimatedEnd` and `analytics.session.activeSpan`, with a tooltip that explains the 30-minute rule.

### R-B. Privacy, visitor identification, sign-in linking and opt-out — [E] (policy), [P] (identify endpoint)

| Identifier        | Where                                                                                                                  | Lifetime                                                 | Purpose                                           | Server retention                                       |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| `anon_id`         | localStorage `vg_anon_id` (seeded once from the legacy `vg_session_id` so existing visitors are not re-counted as new) | until storage cleared or opt-out; **rotated on opt-out** | returning-visitor counts, journey across sessions | raw rows deleted at 30 d (§R-G)                        |
| `session_id` (v2) | localStorage `vg_sess2` `{id,last}`                                                                                    | 30-min inactivity                                        | journey, bounce, funnel per session               | same                                                   |
| `event_id`        | per event, random                                                                                                      | single event                                             | idempotent dedup (`ON CONFLICT DO NOTHING`)       | same                                                   |
| `user_id`         | **server-resolved only**                                                                                               | —                                                        | stitch to a known customer                        | same; FK `ON DELETE SET NULL` honours account deletion |

- **No fingerprinting, no IP storage, no UA storage, no raw referrer, no raw URL.** Pages are recorded as a **`page_key`** template (`pdp`, `plp`, `search`, `cart`, …), never the slug or query string. The props for every event are an **allowlist** per registered event (`app/services/analytics/envelope.py`). Unknown keys are dropped server-side, and PII keys are rejected even if a future registry entry lists them.
- **Opt-out:**
  - `vg_analytics_consent=denied`, or the browser's Global Privacy Control (`navigator.globalPrivacyControl === true`), switches the client to **counts-only mode**. `anon_id` and `session_id` are not sent (the server stores NULL); `event_id` (unlinkable) is still sent so counts stay deduplicated.
  - When the visitor opts out, `vg_anon_id` is deleted. Opting back in creates a fresh id, with no relinking.
  - `denied` keeps disabling GA4 as today.
  - The **decision** for the founder is whether "opt-out" must mean _zero_ first-party collection (stricter than the current doctrine, "anonymised server log regardless of consent"). Counts-only is the recommended middle ground: aggregate demand data is legitimate-interest, and journeys are not collected. **Open decision OD-1.**
- **Sign-in linking** — [P], PR 1A-08:
  - Today's stitch never works (claim 9). The fix is an authenticated `POST /analytics/identify {anon_id, session_id}`, called **once per v2 session** after sign-in through the existing dynamic-imported Supabase browser client (`lib/engagement-api.ts` pattern, so it is off the first-load bundle).
  - It writes `analytics_session_links(session_id pk, user_id, linked_at)`. Rollups join this table; **raw events are never back-filled with `user_id`**.
  - Links are deleted with the raw rows at 30 d, and the table is subject to account deletion (FK cascade).
  - It is postponable because every money and order metric comes from authoritative tables keyed by `customer_id` (§R-I). Only "anonymous browsing before first purchase" journeys need it. **Open decision OD-2:** link or not, and for how long.
- **Sensitive inference ban:** the registry carries no free text, no health, religion or ethnicity categories, and no location finer than district (and location is not collected in 1A at all).

### R-C. Rate limiter for 2 workers behind Cloudflare, Caddy and Vercel, without spoofable IPs — [E]

- **Replace** the per-beacon DB counter on the **v2 path only** with an **in-process limiter** (`app/core/inproc_ratelimit.py`). The v1 path is untouched while the flag is off.
  1. **Global token bucket per worker:** 40 batches/s, burst 80. This protects Postgres no matter who sends. With 2 workers the effective global ceiling is **2 ×** the configured figure, and the plan documents it that way.
  2. **Per-client bucket:** 240 batches/min per key, burst 60, LRU-bounded to 10k keys (≈1 MB per worker). The generous per-key figure is deliberate: many real visitors share one key (the Vercel egress IP, §0-4).
- **Key derivation without trusting client-controlled headers** (`app/services/analytics/client_key.py`):
  - Take the **rightmost** XFF hop. Caddy writes it as its real TCP peer whether it replaces or appends, so a client cannot control it.
  - If that hop is inside the **published Cloudflare ranges** (a static list in code, refreshed by the founder or ops quarterly), use `CF-Connecting-IP` (asserted by Cloudflare).
  - Otherwise use the hop itself. The leftmost XFF entry is **never** used.
  - When Caddy is bypassed (an origin reached directly), a forged header gains the caller only their own bucket, still bounded by the global bucket.
  - **Infra decision OD-3:** lock the OCI origin to Cloudflare ranges (security list) or enable Authenticated Origin Pulls. That turns the residual risk into zero. It is not a code change.
- **Why not Redis or the DB:** a shared limiter must be exact only for abuse that matters. For analytics, a 2× over-admit is harmless, and a DB write per beacon is exactly the load we are removing. The in-process limiter adds no new infrastructure.
- **Over-limit:** HTTP 429 is returned (the browser ignores beacon responses), the batch is dropped and `dropped_rate_limited` is counted (§F monitoring).
- The **v1 limiter and `get_client_ip`** stay unchanged, because other endpoints (OTP and auth) depend on them. Moving those to `client_key` is listed as [P] follow-up FU-1 outside this initiative.

### R-D. Non-blocking, bounded, deduplicated, isolated collection — [E]

- **Request path:**
  - Validation is pure Python and CPU-only.
  - The handler then `submit`s the rows to a per-worker **bounded writer** (`app/services/analytics/writer.py`) and returns. The handler does **no DB I/O**: the v2 limiter is in-process, and the v2 path skips the optional Bearer lookup, because beacons never carry a token (§0-9).
- **Writer:**
  - One daemon thread per worker drains a `queue.Queue(maxsize=256 batches)`.
  - When the queue is full, `submit` returns False and the batch is counted as `dropped_overload`. Back-pressure is a drop, never a wait.
  - The thread coalesces up to 500 rows into **one multi-row `INSERT … ON CONFLICT (event_id) DO NOTHING`**, plus the v1 `product_view` projection, as one transaction with `SET LOCAL statement_timeout = '2s'` and `SET LOCAL lock_timeout = '500ms'`.
- **Isolation:**
  - The single writer thread means **at most one pooled connection per worker** is ever used by analytics (≤ 2 of 10 total). Checkout, payments and orders keep ≥ 4 connections per worker regardless of analytics load.
  - Statement and lock timeouts bound how long that connection is held.
  - Analytics tables have no FKs to transactional tables except `user_id → auth.users ON DELETE SET NULL`, and no triggers. So analytics writes never lock checkout rows.
- **Server-side emits** (funnel and search; PR 1A-05): when `analytics_v2_collect` is on, `record_event_best_effort` and `log_search_query` hand their SQL to the same writer instead of running inline in async handlers. This removes the event-loop block from **cart, checkout, payment and order** requests (§0-6). Idempotency is unchanged (the same SQL, still `ON CONFLICT`).
- **Dedup:**
  - The client generates `event_id` (UUIDv4) per event; the DB primary key with `ON CONFLICT DO NOTHING` makes retries and duplicate flushes free.
  - Client-side, the existing listing-view dedup is kept. The v2 queue drops exact duplicates (same event and props within 1 s, for example React StrictMode double effects).
- **Failure isolation:** every exception in collect v2 and in the writer is swallowed and counted. Collect never returns 5xx for a DB problem, because DB I/O happens after the response.

### R-E. Search-term retention, anonymisation and k-thresholds — [E]

- **At write time** (1A-06, behind `analytics_v2_collect`), `search_log` stores `term = redact(term)`:
  - digit runs of 6 or more (phones, NRC numbers, account numbers) → `#`
  - e-mail addresses → `@`
  - Zambian MSISDN patterns → `#`
  - capped at 120 chars
- `normalized_term` is derived from the **redacted** term.
- **Retention:** after 30 days the daily sweep sets `term = normalized_term` (removing original casing and spelling) and NULLs `user_id` (as today). Rows older than **180 days** are deleted once 1B daily rollups (`analytics_search_daily`) hold the aggregates. The delete is gated on `analytics_v2_rollups`, so it never runs before rollups exist.
- **k-threshold (k-anonymity for terms):**
  - Admin and AI surfaces show a term only if it was searched in **≥ k distinct sessions** (or ≥ k rows when sessions are unknown) in the window. The default is **k = 5**, stored in `platform_config.analytics_term_k_min`.
  - Below-k terms are aggregated into an "other (n)" bucket.
  - `sample_term` (the raw `min(term)`) is **removed** from the admin response in 1B, which returns `normalized_term` only.
- **AI reporting (1C)** receives only rollups that already pass k. Any metric whose underlying count is below **n = 20** is reported as "insufficient data", not as a percentage (minimum sample threshold).

### R-F. A deterministic weekly report that works without AI — [E]

- The weekly report is **generated by SQL plus templating in the API** (`services/analytics/report.py`, `GET /internal/analytics/weekly-report?week=YYYY-Www`), returning `{metrics, deltas, flags, markdown}`.
- Flags are deterministic rules, for example "checkout conversion −20% w/w with n ≥ 20", "zero-result share > 30%" and "ingest drop rate > 1%".
- The AI step in n8n is an **optional enrichment**. It receives the JSON (k-filtered aggregates only, no ids or terms below k) and returns an explanation.
- If OpenRouter fails, times out (20 s) or the AI budget switch is off, n8n sends the deterministic markdown unchanged, with the line "AI commentary unavailable this week".
- The report is also viewable in the admin Insights tab, which reads the same endpoint, so it never depends on n8n or AI to exist.

### R-G. Storage recomputed with explicit assumptions

**Traffic assumptions** (founder to confirm):

- Sessions per day (S): pilot S = 500, month 3 S = 2,000, stretch S = 5,000.
- v2 events per session: 12 = 1 `session_start` + 5 `page_view` + 3 `product_view` + 1.5 `search` + 1.5 other.
- Impressions are **not** in the event log; they stay in `listing_analytics`.

**`analytics_event_log` row width** (PG16, 8 KB pages):

| Part                                                                     | Bytes                                |
| ------------------------------------------------------------------------ | ------------------------------------ |
| Heap tuple header + null bitmap (aligned)                                | 32                                   |
| Line pointer                                                             | 4                                    |
| `event_id` uuid                                                          | 16                                   |
| `received_at`                                                            | 8                                    |
| `client_ts`                                                              | 8                                    |
| `event_name` (~12 chars)                                                 | 13                                   |
| `event_version` smallint                                                 | 2                                    |
| `source_app`                                                             | 9                                    |
| `anon_id`                                                                | 16                                   |
| `session_id`                                                             | 16                                   |
| `user_id` (NULL > 95%)                                                   | ~1                                   |
| `seq` int                                                                | 4                                    |
| `page_key`                                                               | 9                                    |
| `entity_type` (≈40% of rows)                                             | ~4                                   |
| `entity_id` (≈40% of rows)                                               | ~6                                   |
| `props` jsonb (avg; a product_view with 2 uuids ≈ 110, a page_view ≈ 20) | ~70                                  |
| Alignment padding                                                        | ~10                                  |
| **Heap total**                                                           | **≈ 228 B/row** (≈ 35 rows per page) |

**Indexes:**

- PK btree on uuid: 28 B per entry at ~70% fill with random keys → **≈ 40 B/row**.
- BRIN on `received_at`: ≈ 0.
- No other index. Rollups scan one day by BRIN; retention deletes by BRIN.

**Overhead:** +15% for free-space and dead tuples between autovacuum runs → **≈ 310 B/row all-in**.

**Retention:** raw rows **hard-deleted at 30 days**. A DELETE, not an UPDATE: this avoids the double-write bloat of today's NULLing approach, and person links therefore never outlive 30 days. The size below is the **steady state**, not cumulative.

| Object                                                          | Pilot S=500           | S=2,000            | S=5,000            | Today without plan (S=2,000)           |
| --------------------------------------------------------------- | --------------------- | ------------------ | ------------------ | -------------------------------------- |
| `analytics_event_log` steady state (30 d)                       | 6k rows/d → **56 MB** | 24k/d → **223 MB** | 60k/d → **558 MB** | n/a                                    |
| `listing_view_dedup` (≈33 rows/session, ~210 B incl. 3 indexes) | 2-day purge → 7 MB    | 28 MB              | 70 MB              | **+420 MB/month, unbounded (5 GB/yr)** |
| `search_query_log` (~270 B incl. 3 indexes, 1.5/session)        | 180-day cap → 36 MB   | 146 MB             | 365 MB             | +24 MB/month unbounded                 |
| `analytics_events` v1 (`product_view`, ~300 B, 3/session)       | unchanged in 1A       | +54 MB/month       | +135 MB/month      | grows forever (1B decision)            |
| Rollups (1B, long format ≈ 2k rows/day × 80 B)                  | ~5 MB/yr              | ~5 MB/yr           | ~6 MB/yr           | —                                      |
| WAL churn (not counted in DB size; affects I/O and backups)     | ~2× write volume      | ~13 MB/d           | ~33 MB/d           | —                                      |

**Verdict on the "300 MB/month" estimate:**

- As _write volume_, it matches S ≈ 2,700 sessions/day (24k events/day × 310 B ≈ 7.4 MB/day ≈ 223 MB/month at S = 2,000).
- As _storage_, it is **wrong in both directions**. With 30-day deletion the event log is bounded (≈ 220 MB at S = 2,000). Without the dedup purge, `listing_view_dedup` alone outgrows it.
- The **essential storage fix is therefore the dedup purge** (1A-07), not the new log.

**Founder check FC-1 (Supabase plan capacity):**

- Confirm the plan (Free = 500 MB DB, a hard read-only switch when full; Pro = 8 GB disk included, then metered) and the compute size (Micro: 1 GB RAM, low baseline disk IOPS).
- Confirm the current DB size: run `select pg_size_pretty(pg_database_size(current_database()))` in the SQL editor.
- Under **Free**, S = 2,000 is not sustainable once `analytics_events` v1 and the dedup table are included. **Do not enable `analytics_v2_collect` on Free** without first shipping 1A-07.
- The I/O budget matters more than bytes on Micro. This is why writes are coalesced into ≤ 1 INSERT per worker per drain.

### R-H. GA4 — dependency check and recommendation (no removal)

**Dependencies found:**

1. `packages/analytics` (`gtag.ts`, `analytics-provider.ts`, `track.ts` mirror)
2. CSP allowances in `packages/config/src/security-headers.ts` (`ga4Script`, `ga4Connect`, `ga4Img`), consumed by `apps/customer/middleware.ts`, plus a dead allowance in the vendor config
3. Privacy-policy copy in `legal.json` (en/fr/zh), which names GA4
4. The env var `NEXT_PUBLIC_GA4_MEASUREMENT_ID` (presence in Vercel unknown; **FC-2**)
5. A test fixture URL in `scripts/qa/self-test/e2e-portal-bypass.test.mjs` (string only)

**No** server code, report, n8n flow or dashboard reads GA4 data.

**Implications:**

- GA4 is **inert today** (consent is never set, claim 10). Removing it changes no data anyone sees.
- Keeping it costs nothing at runtime while consent is unset (the script is never fetched), and ~0.3 KB gz of mirror code.
- Enabling it would require a consent banner (customer JS plus UX), an update to the cookie policy and acceptance of Google's processing.

**Recommendation:**

- **Keep GA4 dormant and unchanged through Stage 1.** Do not build a consent banner now. The first-party v2 log covers every Stage 1 metric.
- Re-evaluate at the end of 1B. If no GA4-only need emerges (ads attribution, Search Console linking, demographics), remove it in one PR touching items 1–5, with the privacy copy updated in the same PR. **Open decision OD-4.**
- v2 keeps calling the mirror exactly as v1 does, so behaviour is unchanged.

### R-I. Money and commercial metrics only from authoritative tables — [E]

- **GMV, orders, AOV, payment success, refunds, take-rate:** read only from `orders`, `order_items`, `payments` (status), `refunds`, `ledger_*` and `checkout_groups`. Use SQL aggregates via `run_sql_script` (as `compute_gmv_ngwee` already does), **never** from `analytics_event_log` or `funnel_events.snapshot.total_ngwee`.
- **Client events never carry money as a source of truth.** The v2 registry has no `*_ngwee` prop on `purchase`. Client `cart_add`, `checkout_start`, `payment_start` and `order_placed` beacons are still **accepted but skipped** (as v1 does), because the server funnel records them.
- **Funnel in 1B:**
  - Upper steps (sessions → product_view → cart) come from events.
  - Commercial steps come from `checkout_groups` (started), `orders` (placed) and `payments` (succeeded: the status set used by `payment_status.py`).
  - Join keys are `checkout_group_id` and `customer_id`.
  - "Payment reconciliation": the rollup asserts `count(payments succeeded) == count(orders paid)` per day and raises a data-quality flag otherwise. It does not "fix" anything.
- **Bug fix scheduled in 1B (1B-02):** replace `_funnel_snapshot` and `_orders_by_status` PostgREST full selects with SQL `count(*) FILTER (…)` aggregates. This removes the silent 1,000-row truncation (§0-12).

---

## F. `analytics_v2` flag family, rollback, monitoring and compatibility (shared contract)

### F.1 Flags (independent)

| Switch       | Mechanism                                                                             | Default     | Controls                                                                                                                        | Off ⇒                                                                             | Time to take effect                                                                                    |
| ------------ | ------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **tracking** | build-time env `NEXT_PUBLIC_ANALYTICS_V2_TRACKING="1"` on the customer Vercel project | unset (off) | the client emits v2 envelope fields, `page_view`, `session_start`, periodic flush                                               | byte-identical v1 beacons (same keys, same triggers)                              | Vercel env change + redeploy (~3 min), or Vercel _Instant Rollback_ to the prior deployment (~seconds) |
| **collect**  | `feature_flags.analytics_v2_collect` (DB)                                             | `false`     | the API v2 ingest path, the bounded writer, the in-proc limiter, routing server emits through the writer, search-term redaction | the exact v1 code path (DB rate limiter, `product_view`-only, inline emits)       | ≤ 15 s (per-worker TTL cache)                                                                          |
| **rollups**  | `feature_flags.analytics_v2_rollups` (DB)                                             | `false`     | 1A-07 v2 retention jobs (log delete, dedup purge, term scrub), 1B rollup tick, 1C report endpoints                              | ticks return `{"skipped":"flag_off"}`; the v1 retention sweep still runs as today | next tick                                                                                              |

- **Why tracking is an env var:** the customer layout is statically generated (`generateStaticParams`). Reading a DB flag there would make every page dynamic or add a client fetch on 3G. A v2 client talking to a collect-off server is safe, because **v2 batches are a strict superset of v1** (§F.4). The DB switch `collect` is therefore the _remote kill switch_ for all server-side effects, and the env var only governs client bytes.
- **Rollout order:** collect ON in staging → tracking ON in a staging/preview build → acceptance (§1A.5) → production collect ON → production tracking ON for the pilot → rollups ON after 7 days of clean ingest. The founder's "do not enable for all customers until acceptance passes" is met: production tracking stays off until the staging evidence is reviewed.

### F.2 Rollback

| Layer  | Rollback                                                                                                                                                                                                             | Data effect                                              |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Client | unset the env var + redeploy, or Vercel Instant Rollback                                                                                                                                                             | none                                                     |
| Server | `update feature_flags set enabled=false where flag in ('analytics_v2_collect','analytics_v2_rollups')`                                                                                                               | v2 rows stop; v1 continues as before                     |
| Code   | revert the PR(s). The PRs are stacked and each is independently revertible; reverting 03 leaves 02's empty table harmless                                                                                            | none                                                     |
| Schema | the down section in each migration (for example `drop table public.analytics_event_log; delete from feature_flags where flag like 'analytics_v2_%';`). Run **only** after the flags are off and the code is reverted | drops v2 raw data (aggregates in 1B tables are separate) |

There are no destructive changes to existing tables in 1A. The `search_query_log` term scrub and the dedup purge are behaviour changes **gated by `rollups`** and are documented as irreversible _for the affected rows_ (an intended privacy property).

### F.3 Ingestion and DB-impact monitoring — [E]

- **Per worker, in memory:** `accepted`, `deduped` (estimated from INSERT row counts), `rejected_invalid`, `rejected_unknown_event`, `dropped_rate_limited`, `dropped_overload`, `writer_errors`, `writer_batches`, `writer_rows`, `last_write_ms`, `max_write_ms`, `queue_depth`, `last_error_at`.
- `GET /internal/analytics/ingest-stats` (internal token) returns them, plus the flag states. n8n polls it hourly in 1C, and an alert fires on `dropped_* / accepted > 1%` or `writer_errors > 0`.
- **DB impact:** `GET /internal/analytics/storage` (1A-07) returns `pg_total_relation_size` and row estimates for every analytics table, plus `pg_database_size`. The founder digest reports it daily; the alert threshold is 70% of the plan quota (FC-1).
- **Marketplace unaffected (evidence for acceptance):**
  - p95 of `POST /cart/items`, `/checkout`, `/checkout/payment` and `/orders`, before and after enabling collect in staging, using the existing `load/` k6 scripts.
  - Pool wait time (`psycopg_pool` stats logged by the writer).
  - Zero 5xx on collect.

### F.4 Backward compatibility with the v1 envelope — [E]

- **Wire:**
  - The v1 batch is `{session_id?, events:[{event, props, ts?}]}`.
  - The v2 batch is the **same object plus** `v:2`, `anon`, `sid`, `app`, `consent`, and per event `id`, `ev`, `seq`, `page`.
  - A v1 server (collect off) ignores the extra keys (`extra="ignore"` already) and behaves exactly as today. `session_id` keeps its v1 meaning (the legacy persistent id) so `analytics_events.session_id` semantics are unchanged.
- **v1 clients against a v2 server:** the server accepts v1-shaped batches (no `v`). It synthesises `event_id` server-side (no client dedup available), sets `anon_id = session_id` and `session_id = NULL`, and writes `product_view` through the writer.
- **Readers:** `analytics_event_stream` (v1 view), `query_funnel` and the admin dashboards stay correct, because the writer **projects `product_view` into `analytics_events`** in the same transaction, with exactly the v1 row shape (`session_id` = legacy visitor id, no entity columns, same props) and only for newly inserted (deduplicated) rows. The projection is removed only in 1B, after the rollups replace the v1 readers (1B-06, [P]).
- **API response shape** `{accepted, skipped, rejected}` is unchanged.

### F.5 Future-proof event structures for deferred profiles and segments — [E] (structure only)

- **Versioned registry:** `packages/analytics/registry/events.v2.json` is the single source of truth. The Python and TypeScript sides each assert parity in tests.
  - Each event has a `version`, an `entity_type` and a typed prop allowlist.
  - A new module (events marketplace, services booking, promotions, loyalty, new payment method) adds **one registry entry plus one `track()` call**. It needs no migration, because props are jsonb with an allowlist.
  - A breaking prop change bumps `version`; rollups key on `(event_name, event_version)`.
- **Every row carries three identity keys:**
  - `anon_id` (visitor) and `session_id` (journey) **support** profiles and segments later.
  - `user_id` (known customer, server-resolved) **enables** them.
- **Entities are generic:** `entity_type` + `entity_id` (`product`, `listing`, `vendor`, `event`, `service`, `category`, `clip`, `promotion`). Segments can aggregate by entity without new columns.
- **Context keys** let component- and page-effectiveness work (Stage 4) aggregate without new schema: `page_key` (a template, not a URL) and an optional `props.component` (registered values like `home.hero`, `plp.grid`, `pdp.related`).
- **Rollups (1B) are long-format** `(day, metric, dim_key, dim_value, value, sample_n)`. Profile features (Stage 2: category affinity, price band, recency and frequency) become new metrics in the same table, keyed by `user_id` under the 1B access rules, with no new table per feature.
- **Separation of signal kinds** (founder brief §4): `declared` (follows and saves, which are server events), `observed` (views and searches), `transacted` (orders, authoritative) and `inferred` (Stage 2+ only, written to a separate table with `confidence` and `basis_n`, never into the event log).

---

## Stage 1A — Reliable data foundation

### 1A.1 Files and DB objects

| Area     | Path / object                                                                                                              | Change                                                                                                                 |
| -------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Registry | `packages/analytics/registry/events.v2.json` (new)                                                                         | Event registry: name, version, entity_type, props spec                                                                 |
| Client   | `packages/analytics/src/v2/envelope.ts` (new)                                                                              | Types and the pure `buildEvent` and `buildBatch` helpers                                                               |
| Client   | `packages/analytics/src/v2/ids.ts` (new)                                                                                   | `getAnonId`, `touchSession` (30-min rotation), `isCountsOnly` (consent/GPC), `rotateOnOptOut`                          |
| Client   | `packages/analytics/src/v2/page-key.ts` (new)                                                                              | `pageKeyFromPath` template mapper (locale-stripped, no slugs)                                                          |
| Client   | `packages/analytics/src/track.ts`, `events.ts`, `index.ts`, `analytics-provider.ts`                                        | v2 branch behind `NEXT_PUBLIC_ANALYTICS_V2_TRACKING`; periodic flush; queue bound; new events typed                    |
| Client   | `apps/customer/app/[locale]/_components/page-view-tracker.tsx` (new) + `layout.tsx` (1 line)                               | `page_view` on route change (v2 only; renders null)                                                                    |
| Client   | `apps/customer/lib/listing-view-telemetry.ts`, `plp/listing-card.tsx`                                                      | send `surface` (1A-06)                                                                                                 |
| API      | `app/services/analytics/envelope.py` (new)                                                                                 | Registry, validation, PII guard, v1→v2 normalisation                                                                   |
| API      | `app/services/analytics/writer.py` (new)                                                                                   | Bounded single-thread writer, coalesced INSERT, v1 projection, stats                                                   |
| API      | `app/services/analytics/flags.py` (new)                                                                                    | `analytics_flag(name)` TTL-cached, fail-closed                                                                         |
| API      | `app/services/analytics/client_key.py` (new)                                                                               | Trusted client key (rightmost hop + Cloudflare ranges)                                                                 |
| API      | `app/core/inproc_ratelimit.py` (new)                                                                                       | Token buckets (global + LRU per key)                                                                                   |
| API      | `app/routers/analytics_collect.py`                                                                                         | Flag branch: v1 path unchanged, v2 path added                                                                          |
| API      | `app/routers/internal_analytics.py`                                                                                        | `GET /internal/analytics/ingest-stats`, `GET /internal/analytics/storage`                                              |
| API      | `app/services/analytics/funnel.py`, `search_log.py`                                                                        | Route best-effort writes through the writer when collect is on (1A-05); term redaction (1A-06)                         |
| API      | `app/services/analytics/listing_views.py`, `routers/telemetry_views.py`                                                    | Accept and pass `surface` (1A-06)                                                                                      |
| API      | `app/services/analytics/retention.py`                                                                                      | v2 sweeps: log delete 30 d, dedup purge 2 d, term scrub 30 d (1A-07, rollups-gated)                                    |
| DB       | `supabase/migrations/20261112120000_analytics_v2_foundation.sql` (new)                                                     | `analytics_event_log` (+ BRIN, RLS FORCE, service-role only); flag rows `analytics_v2_collect`, `analytics_v2_rollups` |
| DB       | `supabase/migrations/2026111213xxxx_analytics_session_links.sql` (1A-08, [P])                                              | `analytics_session_links`                                                                                              |
| Tests    | `services/api/tests/test_analytics_v2_*.py`, `tests/rls/test_matrix.py` (+ entries), `packages/analytics/src/**/*.test.ts` | §1A.5                                                                                                                  |
| Docs     | `docs/ops/analytics-events.md`, `docs/ops/data-retention.md`                                                               | v2 dictionary, retention table                                                                                         |

### 1A.2 PR breakdown and dependencies (stacked; each is one branch off the previous)

| PR     | Branch                            | Content                                                                                                                                                                                                                                                                                                     | Depends on                   | Tag                         |
| ------ | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | --------------------------- |
| 1A-01  | `feat/intel-1a-01-envelope`       | This plan; registry JSON; TS envelope types and pure builders; Python `envelope.py` (validation, PII guard, v1 normalisation); parity tests. **No runtime wiring**: zero behaviour and bundle change                                                                                                        | —                            | E                           |
| 1A-02  | `feat/intel-1a-02-schema`         | Migration: `analytics_event_log` + BRIN + RLS FORCE (service-role only) + flag rows; RLS-matrix entry; migration replay test                                                                                                                                                                                | 01                           | E                           |
| 1A-03  | `feat/intel-1a-03-collect`        | `flags.py`, `client_key.py`, `inproc_ratelimit.py`, `writer.py`; collect v2 branch; ingest-stats endpoint                                                                                                                                                                                                   | 02                           | E                           |
| 1A-04  | `feat/intel-1a-04-client`         | `ids.ts`, `page-key.ts`; v2 branch in `track` (env-gated), periodic flush, queue bound, counts-only mode, opt-out rotation; `PageViewTracker`                                                                                                                                                               | 01 (wire), 03 (to be useful) | E                           |
| 1A-04b | `feat/intel-1a-04b-client-lazy`   | Move the v2 client runtime (ids, page keys, envelope) into an async chunk loaded on the first v2 event; pre-load events buffer and degrade to the v1 body if flushed first. Needed because with tracking ON the eager runtime put the PDP at 151.4 KB gz (> 150 KB budget); lazy = +0.3 KB ON / +0.1 KB OFF | 04                           | E                           |
| 1A-05  | `feat/intel-1a-05-server-emits`   | Funnel and search best-effort writes go through the writer when collect is on (off the event loop)                                                                                                                                                                                                          | 03                           | E                           |
| 1A-06  | `feat/intel-1a-06-search-listing` | Search-term redaction at write (collect-gated); `surface` on impressions and PDP views                                                                                                                                                                                                                      | 03                           | E (redaction) / P (surface) |
| 1A-07  | `feat/intel-1a-07-retention`      | Rollups-gated sweeps: log delete 30 d, dedup purge 2 d, term scrub 30 d; `/internal/analytics/storage`; chain a flag-gated v2 tick into the (already UTC) n8n retention workflow                                                                                                                            | 02                           | E                           |
| 1A-08  | `feat/intel-1a-08-identify`       | `POST /analytics/identify` + `analytics_session_links` + client call after sign-in                                                                                                                                                                                                                          | 03, 04, **OD-2**             | P                           |
| 1A-09  | `feat/intel-1a-09-optout-ui`      | "Analytics" toggle on `/account/privacy` (calls `setAnalyticsConsent`), i18n keys en/bem/nya/fr                                                                                                                                                                                                             | 04, **OD-1**                 | P                           |

### 1A.2a Implementation status (2026-11-12)

Stack order (each branch is based on the previous one): `01 → 02 → 03 → 04 → 05 → 06 → 07 → 04b`.

| PR             | Status                | Notes                                                                                                                                                           |
| -------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1A-01 to 1A-05 | done                  | As specified                                                                                                                                                    |
| 1A-06          | done (redaction only) | Term redaction plus the zero-result log line. `surface` on impressions [P] is **not done**: it needs listing-card call-site threading and an optional API field |
| 1A-07          | done                  | n8n retention was already UTC, so the v2 tick is chained after the v1 sweep                                                                                     |
| 1A-04b         | done                  | Added during implementation (bundle budget, see §1A.2)                                                                                                          |
| 1A-08, 1A-09   | not started [P]       | Blocked on OD-2 and OD-1                                                                                                                                        |

**Verification:**

- **pytest:** the new and touched analytics suites are green.
- **Full API suite:** no new failures versus `origin/staging`. The remaining failures are environment-only (local PG16 without Supabase roles) and identical on the base.
- **RLS suite:** the same 10 pre-existing failures as the base; all new matrix and ACL cells pass.
- **TypeScript:** vitest, tsc and eslint (new files) green; the i18n sweep is clean.
- **Bundle guard:** green with tracking OFF and ON.

**Before production tracking ON:**

- The PDP first-load JS is at exactly **150.0 KB gz** (budget 150) with tracking ON. Any further PDP growth must be offset.
- FC-1 (Supabase plan) and OD-1 (opt-out semantics) are still open.

### 1A.3 Migration and rollback

- One additive migration (1A-02). It creates a new table, two indexes (PK + BRIN), three policies and inserts two flag rows. It does not touch any existing table.
- The **down** script is in its header. It is safe at any time after the flags are off.
- 1A-08 adds one table (additive), and its down is `drop table`.
- No data backfill. No existing table is altered in 1A: `surface` already exists, and term redaction is a write-time behaviour.

### 1A.4 Performance and security

- **Client:**
  - Bundle delta ≤ 2 KB gz per customer route. The v2 code is ~1.3 KB gz minified (ids, page-key, envelope fields, timer).
  - With tracking off, the v2 branches are guarded by the inlined `process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING`, so the minifier can drop them.
  - No added request on page load: the beacon is still batched, there is one flush per ≤ 15 s while events are pending, and visibility-hide still flushes.
  - No additional storage writes beyond one small localStorage `setItem` per tracked event (`vg_sess2` = `{id,last,seq}`; the sequence must survive navigation, so it is not throttled).
- **API:**
  - Zero DB I/O on the request path for v2 collect.
  - One writer connection per worker at most.
  - INSERTs coalesced (≤ 1 statement per drain).
  - `statement_timeout` 2 s; queue bounded (256 batches × ≤ 20 events).
  - Memory ceiling ≈ 256 × 20 × ~600 B ≈ 3 MB per worker.
- **Security:**
  - Public endpoint: per-key and global limits, body cap (collect keeps `MAX_EVENTS_PER_BATCH = 20`; props ≤ 2 KB serialised).
  - Strict allowlists for event names and props; PII-key rejection (reusing `_PII_KEYS`); UUID validation; timestamps clamped to [now − 7 d, now + 5 min].
  - SQL literals produced only by `sql_literal` / validated-UUID / int formatting (the same seam as existing writers).
  - The table is **service-role only** (no grant to anon or authenticated). Admin reads go through admin-guarded API endpoints in 1B.
  - Internal endpoints use the existing `X-Internal-Token` guard (`INTERNAL_ANALYTICS_TOKEN`).

### 1A.5 Tests and acceptance criteria

| PR  | Automated tests                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Acceptance evidence                                                                                     |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| 01  | Python: registry parity with JSON; v2 validation (allowlist, PII keys, money ints, UUIDs, ts clamp, size cap, unknown event, version mismatch); v1→v2 normalisation. TS: envelope builder shape, registry/type parity                                                                                                                                                                                                                                             | pytest, vitest, ruff, mypy, tsc green; no app file imports v2 (bundle unchanged)                        |
| 02  | Migration replays from 0001 on PG16; RLS matrix: `analytics_event_log` client_invisible for 6 personas × 4 verbs; flag rows present and default false                                                                                                                                                                                                                                                                                                             | `test_no_untested_tables` lists no new gap                                                              |
| 03  | Flag off ⇒ the existing `test_analytics_collect.py` passes unmodified **and** the DB limiter is still called. Flag on ⇒ no `record_event` / DB call on the request thread; writer receives rows; 429 from the in-proc limiter; unknown or invalid events rejected; v1 batch accepted; dedup via `ON CONFLICT` (DB test); writer queue full ⇒ drop counted, never raises; client_key ignores leftmost XFF and honours CF only from CF ranges; ingest-stats guarded | Staging: 1k beacons/min for 10 min ⇒ 0 × 5xx, writer `max_write_ms < 200`, checkout p95 delta < 5% (k6) |
| 04  | Flag off ⇒ existing `track.test.ts` and `session.test.ts` unchanged and green, and the beacon body is byte-identical. Flag on ⇒ envelope fields, seq monotonic, `event_id` unique, session rotates after 30 min idle (fake timers), counts-only on denied/GPC, opt-out rotates anon, queue bound, periodic flush, page-key mapping                                                                                                                                | Customer `next build` + bundle guard ≤ +2 KB on every route                                             |
| 05  | Collect on ⇒ `record_event_best_effort` and `log_search_query` submit to the writer (no inline `run_sql_script`); collect off ⇒ inline exactly as before; failures still swallowed                                                                                                                                                                                                                                                                                | Cart, checkout, payment and order tests unchanged and green                                             |
| 06  | Redaction unit tests (phones, emails, digits, length); impressions carry surface; invalid surface → `unknown`                                                                                                                                                                                                                                                                                                                                                     | —                                                                                                       |
| 07  | Rollups off ⇒ v2 sweeps skipped; on ⇒ batched deletes respect cutoffs (DB test); storage endpoint guarded                                                                                                                                                                                                                                                                                                                                                         | Storage endpoint output attached to the PR                                                              |

**Release acceptance for 1A (all must hold before production tracking ON):**

1. Events from a scripted staging journey (home → search → PDP → cart → checkout) appear exactly once in `analytics_event_log`, with one `session_id`, monotonic `seq` and the correct `page_key`s.
2. A 31-minute idle produces a new `session_id` and a `session_start`.
3. Opting out yields NULL ids.
4. Killing the DB connection for 60 s causes no customer-visible error, and the drop counter rises.
5. Collect OFF reproduces v1 exactly (the existing tests, plus a manual diff of `analytics_events` rows).
6. Bundle guard green.
7. The founder signs off on FC-1 and OD-1.

### 1A.6 Unresolved decisions (1A)

- **OD-1:** opt-out semantics (counts-only versus zero collection).
- **OD-2:** sign-in linking (on/off, 30-day retention).
- **OD-3:** origin lock to Cloudflare (infra).
- **FC-1:** Supabase plan, quota and current DB size.
- **FC-2:** whether `NEXT_PUBLIC_GA4_MEASUREMENT_ID` is set in Vercel.
- **OD-5:** whether the beacon should move from the Vercel rewrite to a direct `api.` post with a `text/plain` body. This would save one hop and make the CF IP a real visitor IP, but needs CORS and CSP review. Recommended for after the pilot.

---

## Stage 1B — Business intelligence

### 1B.1 Files and DB objects

| Area  | Path / object                                                                                           | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| DB    | `…_analytics_rollups.sql`                                                                               | `analytics_daily_rollup(day date, metric text, dim_key text, dim_value text, value bigint, sample_n int, computed_at, PK(day,metric,dim_key,dim_value))`; `analytics_search_daily(day, normalized_term, searches, zero_results, sessions, PK(day,normalized_term))`; `analytics_rollup_runs(day, started_at, finished_at, status, rows, error)`; RLS FORCE service-role only; function `analytics_rollup_day(p_day date)` SECURITY DEFINER, `search_path` pinned, execute granted to service_role only |
| API   | `app/services/analytics/rollup.py`, `routers/internal_analytics.py`                                     | `POST /internal/analytics/rollup-tick` (catch-up of the last 7 missing days, idempotent delete+insert per day, rollups-gated)                                                                                                                                                                                                                                                                                                                                                                          |
| API   | `app/services/analytics/metrics.py`                                                                     | Authoritative commercial metrics (orders, payments, refunds, GMV, AOV) via SQL aggregates (§R-I)                                                                                                                                                                                                                                                                                                                                                                                                       |
| API   | `app/routers/admin_analytics.py` (new, under `admin_base` ⇒ `require_role('admin')`)                    | `GET /admin/analytics/overview                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | search-demand | products-funnel | insights?from&to` reading rollups plus authoritative tables; k-threshold applied |
| API   | `app/routers/admin_dashboards.py`                                                                       | Fix truncating funnel and status counts (SQL `count(*) FILTER`) — **bug fix, E**                                                                                                                                                                                                                                                                                                                                                                                                                       |
| API   | `app/routers/admin_search_insights.py`, `search_log.py`                                                 | Drop `sample_term`; k-threshold                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Admin | `apps/admin/app/[locale]/analytics/{page,search,products,insights}/page.tsx`, `_components/analytics/*` | 4 tabs; charts as accessible SVG/CSS bars (no chart library)                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| i18n  | `packages/i18n/messages/{en,bem,nya,fr,zh}/admin.json` (`analytics.*`)                                  | All copy keyed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Tests | `test_analytics_rollup.py` (DB), `test_admin_analytics.py`, RLS matrix, admin vitest                    | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

### 1B.2 PRs

| PR    | Content                                                                                                                                                                                        | Depends                          | Tag                                            |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ---------------------------------------------- |
| 1B-01 | Rollup schema + `analytics_rollup_day` SQL (sessions, bounce, active span, page_views by page_key, product_views by entity, searches/zero-results by term, funnel upper steps) + tick endpoint | 1A-02, 1A-03                     | E                                              |
| 1B-02 | `admin_dashboards` count-truncation fix                                                                                                                                                        | — (independent, can merge first) | E                                              |
| 1B-03 | `metrics.py` authoritative commercial metrics + payment reconciliation data-quality flag                                                                                                       | —                                | E                                              |
| 1B-04 | `admin_analytics.py` endpoints + k-threshold + `sample_term` removal                                                                                                                           | 01, 03                           | E                                              |
| 1B-05 | Admin UI: Overview, Search & Demand, Products & Funnel, Insights (deterministic flags)                                                                                                         | 04                               | E (Overview, Search) / P (Products tab polish) |
| 1B-06 | Retire the v1 `product_view` projection and point `query_funnel` at rollups; v1 `analytics_events` gets a 180 d delete                                                                         | 01, 05 + 30 days of parallel run | P                                              |

### 1B.3 Migration and rollback

- Additive tables and a function; the down drops them.
- The rollup is **recomputable** from raw for 30 days, so a bad rollup is fixed by re-running the tick for the affected days.
- Turning rollups off freezes the tables; the admin UI shows "data paused since <day>".

### 1B.4 Performance and security

- The rollup runs once a day per day of data, as one SQL function over a BRIN-ranged day (≈ 24k–60k rows): a seconds-scale query.
- It runs at 02:15 UTC (pilot low traffic) with `statement_timeout` 60 s.
- Admin endpoints read **only** rollups and authoritative aggregates, never raw events. They are cached 60 s in process.
- Every route is `require_role('admin')` via `admin_base` (audited).
- Customer-level drill-down is **out of scope** for 1B. Aggregates only; k ≥ 5 for terms; n ≥ 20 for rates.

### 1B.5 Tests and acceptance

- Seeded-day DB tests assert exact rollup values: sessions, bounce, funnel and zero-result share.
- Recomputing a day is idempotent.
- Commercial metrics equal direct SQL over the seeded `orders`/`payments`.
- The admin count fix is verified with 1,500 seeded orders.
- Non-admin gets 403 on every `/admin/analytics/*` route.
- The k-threshold hides a term seen in 4 sessions and shows it at 5.
- **Acceptance:** after 7 days of staging data, the Overview numbers reconcile with `orders`/`payments` exactly, and the founder can answer "what are customers searching for but not finding" from Search & Demand.

### 1B.6 Open decisions

- **OD-6:** k value (default 5) and minimum n (default 20).
- **OD-7:** whether vendor-facing analytics adopt rollups now or stay on `listing_analytics` (recommended: stay; vendor intelligence is deferred).

---

## Stage 1C — Automated intelligence

### 1C.1 Files and DB objects

| Area  | Path / object                                                                       | Change                                                                                                                                                                                                           |
| ----- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| n8n   | `infra/n8n/analytics-rollup.json` (new)                                             | Daily 02:15 UTC → `/internal/analytics/rollup-tick`; retry 3× (5 min); on failure → existing `money-workflow-error-alert` pattern (WhatsApp/email founder); `settings.timezone = "UTC"`                          |
| n8n   | `infra/n8n/weekly-intel-report.json` (new)                                          | Mon 05:30 UTC → `GET /internal/analytics/weekly-report` → _optional_ OpenRouter explain node (timeout 20 s, `continueOnFail`) → merge → send via the existing WhatsApp/Resend nodes; deterministic fallback text |
| n8n   | `infra/n8n/analytics-ingest-alert.json` (new)                                       | Hourly → `/internal/analytics/ingest-stats` (both workers, sampled twice) + `/storage` daily → alert on thresholds (§F.3)                                                                                        |
| n8n   | `infra/n8n/analytics-retention.json`                                                | Already UTC; 1A-07 chains the flag-gated `v2-retention-tick` node                                                                                                                                                |
| API   | `app/services/analytics/report.py`, `routers/internal_analytics.py`                 | Deterministic weekly report (JSON + markdown), k- and n-filtered                                                                                                                                                 |
| API   | `app/services/analytics/ai_explain.py` (optional [P])                               | If AI is run via the API instead of n8n: OpenRouter call with spend cap `platform_config.ai_report_monthly_cap_usd` (default $3), counted in `ask_spend_monthly`-like accounting                                 |
| Admin | Insights tab shows the latest report, with its AI commentary flagged "AI-generated" | —                                                                                                                                                                                                                |
| Docs  | `docs/ops/analytics-runbook.md`                                                     | Flags, rollback, alerts, re-run rollup                                                                                                                                                                           |

### 1C.2 PRs

| PR    | Content                                                                         | Depends      | Tag                             |
| ----- | ------------------------------------------------------------------------------- | ------------ | ------------------------------- |
| 1C-01 | Rollup n8n workflow + failure alert                                             | 1B-01        | E                               |
| 1C-02 | `report.py` deterministic weekly report + endpoint + admin Insights wiring      | 1B-03, 1B-04 | E                               |
| 1C-03 | Weekly report n8n workflow with optional AI enrichment + deterministic fallback | 1C-02        | E (fallback path) / P (AI node) |
| 1C-04 | Ingest/storage alert workflow                                                   | 1A-03, 1A-07 | E                               |
| 1C-05 | AI spend cap + redaction audit (payload is logged as a hash plus key list only) | 1C-03        | P                               |

### 1C.3 Migration and rollback

- No schema, beyond an optional `platform_config` key insert.
- Rollback: deactivate the workflow in n8n. The API endpoints stay idempotent and read-only.
- n8n is never in the customer path. If n8n is down, the rollup can be triggered manually (admin "recompute" button, [P]) or caught up on the next tick (7-day catch-up).

### 1C.4 Performance and security

- n8n load: 1 daily + 1 weekly + 24 hourly executions per day, which is negligible on the OCI VM.
- **No per-click execution.**
- The AI payload contains **no** ids, **no** terms below k, no free text and no vendor names below n. Model output is stored as text and rendered escaped.
- Internal endpoints are token-guarded. The OpenRouter key stays in the n8n credential store (`validate-n8n-no-plaintext-secrets.sh` already enforces this).

### 1C.5 Tests and acceptance

- **Report:** unit tests with fixed rollups → exact markdown snapshot; below-n metrics render "insufficient data"; k-filter applied.
- **Workflows:** JSON lint + the no-plaintext-secrets check; a manual run in staging with the AI node forced to fail still delivers the deterministic report.
- **Acceptance:**
  - two consecutive weekly reports delivered (one with AI disabled)
  - the rollup alert fires when the tick is pointed at a bad token
  - the ingest alert fires on a simulated drop

### 1C.6 Open decisions

- **OD-8:** delivery channel (WhatsApp founder number versus e-mail).
- **OD-9:** AI provider and budget (OpenRouter under the existing $15 kill-switch, or a separate $3 cap).
- **OD-10:** whether AI may see vendor names (recommended: only vendors with ≥ 20 orders in the window).

---

## Essential versus postponable summary

| Essential (foundation is unreliable without it)                                      | Postponable (no loss to the foundation)                                                       |
| ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| 1A-01 to 1A-05 (contract, table, isolated collect, client v2, off-loop server emits) | 1A-08 sign-in identify (needs OD-2)                                                           |
| 1A-06 term redaction                                                                 | 1A-06 `surface` attribution (useful, not foundational)                                        |
| 1A-07 dedup purge, log retention, storage endpoint                                   | 1A-09 opt-out UI toggle (GPC + cookie already honoured)                                       |
| 1B-01 to 1B-04, 1B-05 Overview + Search                                              | 1B-05 Products tab polish, 1B-06 v1 retirement                                                |
| 1B-02 count-truncation fix                                                           | 1C-05 AI spend cap (if AI runs only in n8n under existing caps)                               |
| 1C-01, 1C-02, 1C-03 fallback, 1C-04                                                  | 1C-03 AI node itself, admin "recompute" button, FU-1 (move OTP/auth limiters to `client_key`) |

**Deliberately not built in Stage 1:**

- Profiles, segments, recommendations, propensity or churn models, vendor intelligence.
- GA4 changes, consent banner.
- Partitioning (revisit at > 5M rows in `analytics_event_log`, i.e. S > 10k sessions per day).
- Redis, queues, ClickHouse.
