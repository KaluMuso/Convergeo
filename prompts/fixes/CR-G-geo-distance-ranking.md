> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** One **additive** migration (number assigned = next free `NNNN`). Money stays integer ngwee; this pebble adds geo ranking, no money paths. Run the FULL search test suite before reporting.

# CR-G — Geo-distance ranking in discovery (proximity-first search)

## Finding

The concept's proximity-first discovery — *"sort nearest," "2–3× geo weight for commodities," "around me now," "on the route"* — is **not implemented**. `search_rrf` (defined in `supabase/migrations/0009_search.sql`) ranks on FTS + pg_trgm + optional pgvector via RRF plus `boost_signals` (`in_stock`, `verified`) only — **no distance term**. This is the single biggest concept differentiator still thin in live code, and "found by proximity" is core to beating WhatsApp sellers. The plumbing is already there: `public.search_documents` carries `lat`/`lng` (populated from the first vendor location), and `SearchHit` already exposes `lat`/`lng` — but the search API accepts **no user location** and the ranker ignores distance.

## Required fix (backend ranking — UI location capture is the CR-G2 follow-up)

1. **Additive migration `NNNN_search_rrf_geo.sql`** — `create or replace function public.search_rrf(...)` **mirroring the current signature** (read it in `0009_search.sql`; do NOT edit shipped migrations) plus two optional params `p_user_lat double precision default null`, `p_user_lng double precision default null`. When **both** are non-null, compute great-circle distance (km) from each document's `lat`/`lng` to the user and fold a **bounded, monotonic distance decay** into the final score — near boosts, far attenuates, but distance must **never dominate textual/semantic relevance** (cap the geo contribution; documents with null geo are unaffected, never dropped). When user location is null, behavior is **identical to today** (no distance term). Re-`grant execute … to service_role` (mirror `0050_revoke_definer_execute_from_public.sql`).
2. **Thread the params through**: `call_search_rrf` `rpc_args` (`p_user_lat`/`p_user_lng`), `run_search(...)` (new optional `user_lat`/`user_lng`), and `GET /search` query params `lat`/`lng` (Pydantic-validated: lat ∈ [-90,90], lng ∈ [-180,180]; both-or-neither).
3. **Return `distance_km`** on `SearchHit` when computed (null otherwise) so the UI can show "N km away" and offer a Nearest sort.
4. Keep RRF weights and the no-location ranking path **byte-identical** — this is purely additive.
5. (Optional, same PR only if clean) a modest **stronger geo weight for commodity/Class-C categories** — parameterize but keep the default conservative.

## Files (ONLY)

- Add `supabase/migrations/NNNN_search_rrf_geo.sql`
- Modify `services/api/app/services/search/__init__.py` (`call_search_rrf` args, `run_search` params, `SearchHit.distance_km`), `services/api/app/services/search/query_builder.py` (validate/pass location)
- Modify `services/api/app/routers/search.py` (add `lat`/`lng` query params)
- Add/extend `services/api/tests/test_search.py` (or a new `test_search_geo.py`)
- **Do NOT touch** the `ask/` RAG path, `main.py`, money/orders, or the customer UI (location capture = follow-up CR-G2).

## Tests (RUN)

- With user location: given two documents of **equal** textual relevance, the **nearer** one outranks the farther one; `distance_km` is computed and monotonic. Without location: ranking is unchanged (snapshot the ordering from an existing search test). Null-geo documents still appear and are never dropped. `supabase db reset` replays the new migration clean. Full `uv run pytest -k search` + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (the distance decay formula + geo cap) / TESTS (paste near-outranks-far + unchanged-without-location + null-geo-safe + migration replay) / EXCERPTS (the SQL distance term + the router params) / QUESTIONS.

---

### Follow-up (separate pebble) — CR-G2: customer location capture
Wire an **opt-in** geolocation prompt in `apps/customer` (browser `navigator.geolocation`, with a manual "set my area" fallback and a persisted choice), pass `lat`/`lng` to `/search` + PLP, and render "N km away" + a **Nearest** sort control. Keep it privacy-respecting (explicit consent, coarse precision, no storage of raw coordinates beyond the session). Depends on CR-G.
