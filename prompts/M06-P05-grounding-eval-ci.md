> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **⚠ You are the SOLE editor of `.github/workflows/ci.yml` this wave.** **Run `uv run pytest tests/evals/ -q` before reporting.**

# M06-P05 — Grounding eval set & CI gate

## 1. Context

**Grounded against as-built `master` (M06-P02 `/ask` + `run_ask` MERGED):**

- **`run_ask(*, client, query, user_id, guest_key, model_caller=None, retriever=None) -> AskResponse`** (`services/api/app/routers/ask.py`) is the testable pipeline entry — it accepts injectable `model_caller` and `retriever`, so evals run **deterministically without a live API key** by passing a recorded/mocked `model_caller` and a fixture retriever. Reuse it; do NOT edit `ask.py`.
- **Grounding invariants to assert:** zero fabricated listings (every cited `entity_id` ∈ the retrieved set — `validate_citations` already enforces this in prod; the eval proves it end-to-end), ZMW correctness (ngwee→decimal), refusal on trap/no-answer questions (`refused: true`).
- **CI:** `.github/workflows/ci.yml` — add an **eval job** that runs on `ask/**` changes + nightly (`schedule`), using fixtures (no live key). Mirror the existing `python` job's uv setup. **Only this pebble edits `ci.yml` this wave.**
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P05.

## 2. Objective & scope

A 20-question grounding eval set + deterministic CI gate: exact / fuzzy / semantic / price-filtered / no-answer-trap questions, each with recorded model responses + fixture retrieval, asserting no fabricated listings, ZMW-correct citations, and refusal on traps. Runs in CI with no live API key; a live-mode flag for local runs.
**Non-goals:** no `ask.py`/`quota.py` change; no new model integration.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/tests/evals/ask_eval_set.yaml` (20 questions with fixture retrieval + recorded model answers + expected outcome) · `services/api/tests/evals/test_ask_grounding.py` (loads the yaml, drives `run_ask` with injected fixture retriever + recorded `model_caller`, asserts grounding) · `services/api/tests/evals/__init__.py` if needed
- **Modify:** `.github/workflows/ci.yml` (add the `ask-evals` job — `on: pull_request` path-filtered to `services/api/app/services/ask/**` + `services/api/app/routers/ask.py` + `services/api/tests/evals/**`, plus a nightly `schedule`; uv setup like the `python` job; NO Postgres needed — pure fixtures)
  **Guardrail: nothing else. Do NOT touch `ask.py`/quota/retrieve/citations, seed data, other ci jobs' steps.**

## 4. Implementation spec

- **`ask_eval_set.yaml`:** 20 entries: `{ id, category (exact|fuzzy|semantic|price_filtered|no_answer), query, fixture_docs: [{entity_kind, entity_id, title, body, price_min_ngwee, price_max_ngwee}], recorded_answer: {answer_text, cited_entity_ids, model, total_tokens}, expect: {refused: bool, cited_ids: [...], zmw_contains?: "K..."} }`. Include ≥4 no-answer traps (empty `fixture_docs` → expect `refused: true`) and ≥3 price-filtered.
- **`test_ask_grounding.py`:** parametrize over the yaml; build a fixture retriever returning the entry's `fixture_docs`; build a `model_caller` returning the `recorded_answer`; call `run_ask`; assert: no cited id outside `fixture_docs`; `refused` matches; ZMW decimal correct where `zmw_contains` set. A `--ask-live` flag (env `ASK_EVAL_LIVE=1`) swaps in the real `call_answer_model` for local-only runs (skipped in CI).
- **`ci.yml`:** add job `ask-evals` (uv sync + `uv run pytest tests/evals -q`), path-filtered + nightly schedule. Do not alter existing jobs.

## 5–9. Security etc.

No secrets in fixtures; CI job runs with NO live API key (deterministic); recorded answers are static fixtures.

## 10. Tests (RUN before reporting)

`uv run pytest tests/evals/ -q` → 20/20 grounded on fixtures; trap questions refuse; ZMW-decimal assertions pass. `uv run ruff check tests/evals`, `uv run mypy tests/evals`. **Validate the ci.yml YAML** (`python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`).

## 11. Acceptance criteria / DoD

- [ ] 20/20 grounded on fixtures; trap questions refuse; eval runs in CI **without a live API key**; live-mode flag works locally.
- [ ] `ci.yml` valid + only adds the `ask-evals` job (no other job changed); ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P05 — Grounding eval set & CI gate
**STATUS/FILES/DEVIATIONS** (the fixture-injection approach; the ci.yml job trigger + path filter) **/TESTS** (paste the 20-question eval run tail + ruff/mypy + yaml-validate) **/EXCERPTS** the `run_ask` fixture-injection harness + the ci.yml job block — nothing else **/QUESTIONS**
