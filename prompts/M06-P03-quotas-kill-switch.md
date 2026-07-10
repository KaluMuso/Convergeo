> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0024` (ask usage/spend) this wave** (renumber to next free slot if claimed at merge). **Run the FULL `uv run pytest` before reporting.**

# M06-P03 — Quotas, kill-switch & abuse filters

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **⚙ You wrap M06-P02's `/ask` (parallel):** M06-P02's `ask.py` calls `app.services.ask.quota.check_and_reserve(...)` **before** the model call and `record_answer(...)` **after** a non-cached answer (both import-guarded on P02's side). **You create `quota.py` + `spend.py` providing exactly those functions.** Cache hits do NOT call `record_answer` (P02 skips) — so your decrement is per _answered, non-cached_ question.
- **Limits from `platform_config`:** guest **3 lifetime** (device/IP-keyed) → signup prompt; free **25/mo**; **global $15/mo kill-switch**. Config-driven (D-spec).
- **Spend meter:** token→USD (per-model rate from config), monthly aggregate; **kill-switch checked pre-call** → hard-stop with a friendly i18n message; **admin-resettable**.
- **Usage table (migration `0024_ask_usage.sql`):** per-question usage rows + monthly aggregate (this is the AI-usage source the M13-P09 dashboard tile will read once live). RLS service-role/admin.
- **Abuse filters:** length caps, rate limit, repeated-identical spam, off-topic/PII prompt screen.
- **i18n `ai` (append-rule):** append `ai.quota.*` (M06-P02 appends `ai.answer.*` — disjoint sections).
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P03.

## 2. Objective & scope

Quota + spend enforcement for Ask Vergeo: guest 3-lifetime / free 25-mo (config), token→USD meter with **$15/mo kill-switch** (pre-call hard-stop, admin-resettable), abuse filters — exposed as `check_and_reserve`/`record_answer` that M06-P02 calls. Decrement exactly once per answered non-cached question.
**Non-goals:** no RAG/retrieval (M06-P02 — you're called by it), no Ask UI (M06-P04), no dashboard tile (M13-P09 reads your table later).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/ask/quota.py` (`check_and_reserve`, `record_answer`, guest/free limits, abuse filters) · `services/api/app/services/ask/spend.py` (token→USD meter, monthly aggregate, kill-switch) · `supabase/migrations/0024_ask_usage.sql` · `services/api/tests/test_ask_quota.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/ai.json` (append `ai.quota.*` — limit/kill-switch messages)
  **Guardrail: nothing else. Do NOT touch `ask.py`/`retrieve.py`/`cache.py` (M06-P02 — it calls you), `main.py`, db.ts beyond `0024`.**

## 4. Implementation spec

- **`quota.py`:** `check_and_reserve(*, user_id|guest_key)` → enforce guest-3-lifetime (device/IP heuristic, documented best-effort) / free-25-mo (config) + abuse filters (length cap, rate limit, repeated-identical, off-topic/PII screen) + kill-switch (`spend.py`); raise a friendly i18n `ai.quota.*` error on breach. `record_answer(*, tokens, model)` → decrement quota + meter spend (**once**, non-cache). Concurrent decrements race-safe (atomic counter / row lock).
- **`spend.py`:** token→USD (per-model config rate, `Decimal` — no float on money-adjacent math), monthly aggregate in `ask_usage`, `is_killed()` pre-call check at ≥$15, `reset_kill_switch()` (admin).
- **`0024`:** `ask_usage` (question rows: user/guest key, tokens, usd_micros or ngwee-equivalent integer, model, created_at) + a monthly-aggregate view/query; RLS service-role/admin.

## 5–9. Security etc.

Quota decrements exactly once per answered non-cached question; **cache hits do not decrement**; kill-switch trips at $15 + admin-resettable; guest quota survives cookie clear via IP heuristic (documented); money math integer/`Decimal` (no float); abuse filters enforced; no secrets.

## 10. Tests (RUN before reporting)

`test_ask_quota.py`: **quota boundary** (3rd guest Q ok, 4th blocked; free 25 boundary); **month rollover**; **kill-switch trip at $15 + reset**; **concurrent decrements race-safe** (N parallel → exactly N decrements, none lost/double); cache-hit-does-not-decrement (assert `record_answer` not called on hit path — via P02 contract). `0024` replay note. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Quota decrements exactly once per answered question; cache hits don't decrement; kill-switch trips at $15 + admin-resettable; guest quota IP-heuristic documented.
- [ ] `0024` additive+reversible; `check_and_reserve`/`record_answer` match P02's call sites; `ai.quota.*` appended (append-rule); full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P03 — Quotas, kill-switch & abuse filters
**STATUS/FILES/DEVIATIONS** (the exact `check_and_reserve`/`record_answer` signatures P02 imports; spend rate source; IP-heuristic approach) **/TESTS** (paste quota-boundary + rollover + kill-switch + race-safe + full-pytest tail) **/EXCERPTS** the atomic decrement + the kill-switch pre-call check — nothing else **/QUESTIONS**
