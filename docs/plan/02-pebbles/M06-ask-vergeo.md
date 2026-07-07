# M06 — AI Mode "Ask Vergeo" — Pebbles

6 pebbles. RAG grounded ONLY in `search_documents`; quotas + $15/mo kill-switch are config-table-driven (M03-P07). OpenRouter via server-side key only.

---

### M06-P01 — Embedding pipeline `M`
**Deps:** M03-P08, M05-P05 · **Files:** `services/api/app/services/embeddings/` (client: OpenRouter cheap model w/ gte-small fallback, batcher, retry/backoff), `app/routers/internal_embeddings.py` (n8n-cron-invoked batch endpoint, internal-token guard), migration `supabase/migrations/00xx_embedding_jobs.sql` (job queue rows enqueued by search_documents triggers), `scripts/embed_backfill.py`, `infra/n8n/embeddings-cron.json`
On publish/update → job row → batch embed (≤64/req) → write `search_documents.embedding`; backfill CLI; failure retry with dead-letter after 5 attempts; cost logged per batch.
**AC:** new listing searchable semantically ≤5min; batch idempotent (re-run no-ops); dead-letters visible in admin data.
**Tests:** batcher unit tests (partial failure, retry, idempotency); dimension mismatch guard.

### M06-P02 — RAG answer API `L`
**Deps:** P01 · **Files:** `services/api/app/routers/ask.py`, `app/services/ask/` (filter-extraction step, retrieval via `search_rrf`, grounding prompt template, answer schema, citation resolver, response cache table migration `00xx_ask_cache.sql`)
`POST /ask`: extract structured filters (price/category/location) → retrieve top-k → answer STRICTLY from retrieved docs (system prompt forbids outside knowledge; "I couldn't find that on Vergeo5" fallback) → text + cited listing card refs; ZMW via formatK-equivalent server formatting; per-answer token caps; normalized-query response cache (24h TTL).
**AC:** answers cite only retrieved entity_ids (validator strips others); no-result queries refuse gracefully; p95 <6s; cache hit skips model call.
**Tests:** citation-validator tests (fabricated id stripped); filter extraction fixtures; cache hit/miss; prompt-injection in listing content does not change instructions (guard test).

### M06-P03 — Quotas, kill-switch & abuse filters `M`
**Deps:** P02 · **Files:** `services/api/app/services/ask/quota.py`, `app/services/ask/spend.py` (token→USD meter, monthly aggregate), migration `00xx_ask_usage.sql`, `services/api/tests/test_ask_quota.py`
Guest 3 lifetime (device/IP-keyed) → signup prompt; free 25/mo; limits read from `platform_config`; **global $15/mo kill-switch**: spend meter checked pre-call, hard-stops with friendly i18n message; abuse filters (length caps, rate limit, repeated-identical spam, off-topic/PII prompt screen).
**AC:** quota decrements exactly once per answered question; **cache hits do not decrement** (near-zero marginal cost); kill-switch trips at $15 and admin-resettable; guest quota survives cookie clear via IP heuristic (best effort, documented).
**Tests:** quota boundary (3rd vs 4th guest Q); month rollover; kill-switch trip + reset; concurrent decrements race-safe.

### M06-P04 — Ask Vergeo UI `M`
**Deps:** P03, M02 · **Files:** `apps/customer/app/[locale]/(shop)/ask/page.tsx`, `(shop)/_components/ask/` (thread view, answer bubble w/ cited listing cards, quota banner, signup prompt), zero-results teaser wiring in `(shop)/_components/search/zero-results.tsx` (owned by M05-P06 — **modify here, sequenced in a later wave than M05-P06**), `packages/i18n/messages/en/ai.json`
Dedicated tab (bottom-nav slot) + entry from search zero-results; streaming answer display; cited ProductCard/EventCard rows; quota states (guest countdown, signup CTA, monthly-cap, kill-switch downtime message).
**AC:** works logged-out (guest quota); cards deep-link to PDP/event; 360px thread usable; no raw model text without citation cards when results existed.
**Tests:** quota-state renders; stream error mid-answer; citation card mapping.

### M06-P05 — Grounding eval set & CI gate `M`
**Deps:** P02 · **Files:** `services/api/tests/evals/ask_eval_set.yaml` (20 questions: exact/fuzzy/semantic/price-filtered/no-answer traps), `services/api/tests/evals/test_ask_grounding.py`, `.github/workflows/ci.yml` (add eval job — nightly + on ask/** changes; **only this pebble edits ci.yml this wave**)
Evals against seed data with recorded/mocked model responses for determinism in CI + live-mode flag for local runs; assertions: zero fabricated listings, ZMW correctness, refusal on trap questions.
**AC:** 20/20 grounded on seed; trap questions refuse; eval runs in CI without live API key (fixtures).
**Tests:** the eval suite itself + fixture-recorder tooling.

### M06-P06 — Query analytics & zero-result mining `S`
**Deps:** P02, M05-P05 · **Files:** `services/api/app/services/analytics/search_log.py`, migration `00xx_search_analytics.sql` (query log: term, entity counts, zero_result bool, ask vs search), `services/api/app/routers/admin_search_insights.py` (admin-role data endpoints for M13-P09)
Log every search + ask query (anonymized: no user id retained past 30d, DPA-aligned); aggregates: top terms, zero-result terms, ask cost/day — feeds admin dashboard + merchandising decisions.
**AC:** logging adds <5ms (fire-and-forget); zero-result report matches fixtures; retention job trims PII.
**Tests:** aggregate queries; retention trim; admin-only access.
