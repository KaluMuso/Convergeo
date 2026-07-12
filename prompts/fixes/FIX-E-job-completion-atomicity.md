> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-E — Service-job confirm strands funds + raw-UPDATE audit gap (🟡 #7 + 🟢 #8)

## Findings

- **#7 MAJOR** `services/api/app/routers/job_completion.py:415` — `confirm_job_completion` runs 5 independent non-atomic steps (each `run_sql_script`/`post_transaction` spawns its own psql process — no enclosing transaction). Step 3 `_complete_order` flips `orders.status placed→completed` BEFORE step 4 `_release_service_order` posts `RELEASE_TO_VENDOR`. A failure between them leaves the order looking done while the vendor is never paid — stranded escrow.
- **#8 MINOR** `job_completion.py:239` — `_complete_order` is a raw `UPDATE orders SET status='completed'` that omits the `set_config('app.order_actor'/'app.order_note')` GUCs that `transition_order` (orders/state.py:394) sets, so the audit `order_events` row records a NULL actor.

## Required fix

- **Make confirm recoverable / correctly ordered (#7):** the escrow release (`RELEASE_TO_VENDOR`, idempotency `release-{order_id}`) is already idempotent — reorder so the vendor RELEASE is posted **before** (or atomically with) flipping the order to `completed`, OR make the whole confirm safely re-runnable so a partial failure re-drives to completion (the release key already guarantees exactly-once). Net invariant: **an order cannot be `completed` unless its vendor RELEASE has posted.** Add a test that injects a failure after complete-before-release and proves no stranded state (re-run completes the release; single release overall).
- **Fix the audit actor (#8):** route the `placed→completed` change through the guarded `transition_order` path (orders/state.py) OR set the `app.order_actor`/`app.order_note` GUCs in the same psql script before the UPDATE, so the audit row records the real actor. Keep the guard + audit triggers firing.

## Files (ONLY)

- Modify `services/api/app/routers/job_completion.py` (+ reuse `services/api/app/services/orders/state.py`'s `transition_order` if that's the cleaner path — importing/calling it is fine; do not restructure state.py)
- Add/extend `services/api/tests/test_job_completion.py`
- **Do NOT touch** engagement.py/commissions, db.ts, migrations, other routers.

## Tests (RUN)

Failure-injection: simulate a failure between complete and release → assert the order is NOT left completed-without-release (either it didn't complete, or a re-run drives the single release); double-confirm still releases exactly once (`release-{order_id}`). Audit: after confirm, the `order_events` row for the completion has a non-NULL actor. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS/FILES/DEVIATIONS (the reorder/recoverability approach; the actor-GUC fix) /TESTS (paste failure-injection-no-strand + single-release + audit-actor-present + full-pytest tail) /EXCERPTS the reordered confirm→release + the actor GUC set /QUESTIONS.
