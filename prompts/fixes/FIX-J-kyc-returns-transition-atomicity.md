> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. **⚠ STATE MACHINE — failure-path / concurrency tests required.** Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-J — KYC + Returns transitions are read-then-write (TOCTOU); make them compare-and-swap

## Finding

Orders and Disputes transition atomically (Orders `services/orders/state.py` uses `FOR UPDATE` row locks; Disputes `services/disputes/state.py:308-318` uses compare-and-swap `.update(...).eq("id",…).eq("status", snapshot.status.value)`). Two guarded machines do **not**:

- **KYC** — `services/api/app/services/kyc/state_machine.py` loads the vendor (`_load_vendor`), runs `_guard_transition`, then `_update_vendor` (`:279-289`) does `.update(payload).eq("id", vendor_id)` with **no CAS and no row lock**. The DB trigger `guard_vendor_status_update` (`supabase/migrations/0002_identity_vendors.sql:124-144`) **early-returns for `service_role`**, so it gates _who_ writes status, not _whether the transition is legal_ — the app guard is the only enforcement, and it is non-atomic. Two concurrent `transition_submit` (or approve/reject) calls can both pass the guard and double-write.
- **Returns lane-1** — `services/api/app/services/returns/lane1.py` approve (`:410-424`) and reject (`:512`) do `if status != "requested": 409` then `.update({...}).eq("id", return_id)` — check-then-update, no CAS. (The same file already uses the safe idiom `.eq("status","requested")` at `:553` for another path — apply it here too.) No DB trigger guards `returns.status`.

## Required fix

- Add **compare-and-swap** to both writes, mirroring Disputes: append `.eq("<status_col>", <expected_status>)` to the update, and treat **zero rows affected** as a lost race → raise the uniform conflict error (409, e.g. `kyc_transition_conflict` / `return_transition_conflict`) instead of returning success. Keep the existing guard (it gives the correct pre-check error message); the CAS closes the TOCTOU.
- KYC: the expected status is the loaded `from` status; guard-then-CAS-update. Keep the audit write.
- Returns lane-1: `.eq("status","requested")` on approve/reject; 409 when unaffected.
- No behavior change on the happy path; only concurrent duplicates now lose cleanly.

## Files (ONLY)

- Modify `services/api/app/services/kyc/state_machine.py`
- Modify `services/api/app/services/returns/lane1.py`
- Add/extend `services/api/tests/test_kyc_state.py` and `services/api/tests/test_returns_lane1.py` (or the existing equivalents)
- **Do NOT touch** `returns/lane2.py` (FIX-I owns it), disputes/_, orders/_, migrations, `db.ts`.

## Tests (RUN)

- **KYC race:** two concurrent identical transitions on one vendor → exactly one succeeds, the other 409s; final status is the single expected value (use the real-PG DB fixture, mirroring the disputes concurrency test).
- **Returns race:** two concurrent approves (or approve+reject) on one `requested` return → exactly one wins, the other 409s.
- Happy-path single transition still succeeds; illegal transition still rejected by the guard. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (the CAS predicate + zero-rows→409 handling for each) / TESTS (paste both race tests proving exactly-one-wins + full-pytest tail) / EXCERPTS (the two CAS updates) / QUESTIONS.
