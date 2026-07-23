> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **⚙ do NOT use `git stash`.** No migration. **⚠ MONEY PATH — heightened review; failure-path tests required.** Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-L — Remove the manual-escrow ledger stub fallback (admin_orders, TODO(M08-P05))

## Finding

`services/api/app/routers/admin_orders.py:658-720` — `post_manual_escrow_transaction` prefers the real ledger engine (`_load_ledger_post_transaction()`), but when that lazy import returns `None` it falls back to `_stub_post_manual_escrow`, which posts a manual escrow hold/release **without** going through the ledger engine (it builds balanced postings and writes a synthetic `kind=…|manual|key=…` row). The `TODO(M08-P05)` says: "remove stub once ledger engine is always available in all environments." This is the only substantive stub left on a money path — a manual admin escrow hold/release that, in any environment where the lazy import fails, silently takes a different (non-engine) accounting path than the real ledger.

## Required fix

- **First, establish the invariant** that `_load_ledger_post_transaction()` is always available in production (and in the CI money-DB job). Confirm _why_ the lazy-import guard exists (circular-import avoidance vs genuine optional dependency) — grep the loader and its import chain.
- If the engine is genuinely always present in prod/CI: **delete `_stub_post_manual_escrow` and its call site**; when `_load_ledger_post_transaction()` returns `None`, raise a clear 5xx (`ledger_engine_unavailable`) instead of silently posting via the stub — a manual escrow must never post through a non-audited path. Keep the idempotency key + dual-note enforcement.
- If the lazy import is load-order defensive only, replace the `None` branch with an assertion/eager import so the engine is guaranteed, then drop the stub.
- Do **not** change the ledger templates, the postings math, or `enforce_dual_note`.

## Files (ONLY)

- Modify `services/api/app/routers/admin_orders.py`
- Add/extend `services/api/tests/test_admin_orders.py` (or the existing manual-escrow test)
- **Do NOT touch** the ledger engine (`services/ledger/*`), migrations, `db.ts`, other routers.

## Tests (RUN)

- Manual escrow hold + release each post via the **ledger engine** (assert the returned `transaction_id` came from the engine, `manual=True`, postings balance to 0, idempotent replay = no double-post).
- Engine-unavailable → **raises `ledger_engine_unavailable` (5xx), posts nothing** (no synthetic stub row).
- Dual-note enforcement + idempotency-key behavior unchanged. **Full `uv run pytest`** (incl. the money-DB job) + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (why the lazy import existed + how you guaranteed the engine) / TESTS (paste engine-path + engine-unavailable-raises + idempotent-replay + full-pytest tail) / EXCERPTS (the removed stub + the new raise) / QUESTIONS.
