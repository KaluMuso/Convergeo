> **✅ IMPLEMENTED directly on branch `claude/convergeo-codebase-review-a5wvgp` (2026-07-21).** `services/api/app/services/returns/lane2.py` + `tests/test_returns_lane2.py` unified on bps; the lossy `bps // 100` pct hop is gone. Verified: `test_returns_lane2.py` 19/19 pass, ruff + mypy clean; regression golden proves 1250 bps → 12.5% (25 000 ngwee), not 12% (24 000). **This prompt is retained as the spec/record — do NOT re-run in Cursor.**

> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. **⚠ MONEY PATH — heightened review; failure-path tests required.** Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-I — Restocking fee has two representations (bps vs pct) that diverge (💰)

## Finding

The restocking fee is read two incompatible ways:

- **bps (canonical):** `services/api/app/services/refunds/config.py::load_restocking_fee_bps` reads `platform_config.restocking_fee_bps` (default `1000`, clamp `500–1500` via `refunds/math.py::normalize_restocking_fee_bps`). The disputes path uses bps directly (`services/api/app/services/disputes/service.py:167-168`), and lane-1 refund math is `floor(item × bps / 10000)` (`refunds/math.py:19-23`).
- **pct (lossy):** `services/api/app/services/returns/lane2.py:20-25,113-150` reads a **different** key `restocking_fee_pct` (default `10`, clamp `5–15`), and when that key is absent falls back to `normalize_restocking_pct(bps // 100)` — **integer-truncating bps to whole percent** (`lane2.py:149-150`).

Consequence: with an admin-set `restocking_fee_bps = 1250` (12.5%), a change-of-mind return refunds at **12%** while the same order via a dispute refunds at **12.5%** — a cross-path money inconsistency. Bounded (stays 5–15%) but real, and it violates the single-source-of-truth rule for a money figure.

## Required fix

- **Unify on integer bps as the single representation and `restocking_fee_bps` as the single config key.** Route lane-2 through the shared `refunds/math.py` bps helpers (same as lane-1 / disputes): read the fee with `load_restocking_fee_bps(...)` and compute the lane-2 breakdown from bps — **eliminate the pct intermediate and the lossy `bps // 100` fallback**.
- Retire `restocking_fee_pct` / `load_restocking_pct` / `normalize_restocking_pct` / `_restocking_bps_from_pct` from `lane2.py` (or make them thin bps-preserving shims if a pct is needed only for _display_, never for the money calc). Delete the `TODO(M09-P08)` once the admin surface reads the same `restocking_fee_bps` key.
- Preserve current default behavior when config is absent: `1000` bps = 10%. Keep the 500–1500 clamp as the one clamp.

## Files (ONLY)

- Modify `services/api/app/services/returns/lane2.py`
- Modify `services/api/app/services/refunds/config.py` **only if** a shared reader needs exposing (keep `load_restocking_fee_bps` the single reader)
- Add/extend `services/api/tests/test_returns_lane2.py` (or the existing lane-2 test)
- **Do NOT touch** `refunds/math.py` (bps math is correct), `disputes/*` (already bps), `returns/lane1.py` (FIX-J owns it), migrations, `db.ts`.

## Tests (RUN)

- **Cross-path parity:** set `restocking_fee_bps = 1250`; assert the lane-2 restocking amount for an item equals the disputes/lane-1 amount to the ngwee (both 12.5%).
- Absent config → both paths use 1000 bps (10%). Clamp holds at the 500 / 1500 bounds. Existing lane-2 refund tests stay green. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (confirm pct is gone from the money calc; note any display-only pct kept) / TESTS (paste the 1250-bps cross-path parity assertion + absent-config + clamp + full-pytest tail) / EXCERPTS (the unified bps read/compute) / QUESTIONS.
