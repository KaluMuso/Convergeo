> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P10 — Open-now: evaluate the hours we already store `[CODE]`

## 1. Context
**Wave W4 (discovery completion).**

`vendor_locations.hours jsonb` has existed since migration `0002` and is already **returned** by `directory.py` (lines ~222, ~523, ~708) and other read paths. It is **never evaluated** — nothing anywhere answers "is this vendor open right now?". That is the entire gap: the data is present, the predicate is missing.

Do not add a second hours model. Do not migrate the column shape unless it is genuinely unable to express a normal Zambian trading week — and if so, say why in the report before changing it.

**Type:** `[CODE]`.

## 2. Objective & scope
An `open_now` computation and filter across directory and catalog, correct at boundaries.
**Non-goals:** holidays/closures calendar (note it as a follow-up); maps (**R02-P11**).

## 3. Files (edit ONLY these)
- `services/api/app/services/vendors/hours.py` (new — the single predicate)
- `services/api/app/routers/directory.py`, `catalog.py` — filter + response field
- `apps/customer` directory/PLP filter UI
- `packages/i18n/messages/en/{directory,search}.json`
- Tests

## 4. Implementation spec
- One pure function: `is_open_at(hours: dict, at: datetime, tz: str) -> bool`, plus `next_open_at(...)` for the "opens at 08:00" affordance.
- **Africa/Lusaka (UTC+2, no DST)** is the reference zone; take it from config, never from the client's clock — a device with a wrong clock must not change what the server says is open.
- Handle, with tests: a closed day; a day with no entry at all (treat as closed, not open — fail closed); **overnight spans** crossing midnight (`18:00–02:00`); a span exactly at its open and close minute; malformed/partial JSON (treat as unknown → **excluded from an `open_now=true` filter**, never crash the route).
- Filtering is opt-in (`?open_now=true`). Default listings are unchanged so nothing currently working changes shape.
- Return `open_now` and `next_open_at` on location payloads so the UI need not recompute — but keep it additive.

## 5. Security / conventions
No new dependency for timezone maths if the stdlib `zoneinfo` suffices. Zero hardcoded strings. Cheap enough to run inside existing list queries — do not add an N+1.

## 10. Tests (RUN before reporting)
- `test_open_now_true_inside_span` / `false_outside`
- `test_overnight_span_is_open_after_midnight`
- `test_missing_day_is_closed_not_open`
- `test_malformed_hours_never_raises_and_is_excluded_from_open_now_filter`
- `test_boundary_minutes_inclusive_exclusive` (state the chosen convention in the docstring)
- `test_server_timezone_wins_over_client_clock`
- Route tests: `?open_now=true` narrows the set; default result set is byte-identical to before this pebble.

## 11. Acceptance criteria / DoD
- [ ] One shared predicate; no duplicate hours logic.
- [ ] Boundary, overnight, missing-day and malformed cases tested.
- [ ] Filter opt-in; default responses unchanged.
- [ ] No N+1 introduced.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P10 — Open-now
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** … · **EXCERPTS:** the predicate · **QUESTIONS:** …
