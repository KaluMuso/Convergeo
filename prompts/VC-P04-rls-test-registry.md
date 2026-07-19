> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P04 — Close the RLS test-matrix registry gap `[CODE]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §5 hygiene. **Finding:** `event_categories` (0036), `product_relations` (0052), `service_reviews` (0054) are RLS-enabled **with policies** but are **absent from the RLS test-matrix registry** (`tests/rls/test_matrix.py` `EXPECTATIONS`), which `test_no_untested_tables.py` is meant to catch. **This pebble is the sole editor of `tests/rls/*`** this wave — it also lands the FORCE-RLS expectations for VC-P02's three tables.
**Type:** `[CODE]`.

## 2. Objective & scope
Add the missing tables (× persona × verb) to the RLS matrix so every live table is tested, and reflect VC-P02's FORCE-RLS change.
**Non-goals:** the FORCE migration itself (VC-P02); non-RLS tests.

## 3. Files (edit ONLY these)
- `services/api/tests/rls/test_matrix.py`
- `services/api/tests/rls/test_no_untested_tables.py` (if an allowlist entry needs removing)
**Guardrail: sole editor of `tests/rls/*` this wave (VC-P02 must not touch these).**

## 4. Implementation spec
- Add `EXPECTATIONS` rows for `event_categories`, `product_relations`, `service_reviews` matching their real policies (public-read / owner-write / admin patterns).
- After VC-P02 lands, assert `relforcerowsecurity=true` for `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations` in the matrix (coordinate merge order).
- Ensure `test_no_untested_tables` passes with all three present (drop any stale allowlist).

## 10. Tests (RUN before reporting)
- `uv run pytest services/api/tests/rls -q` green against real PG.
- `test_no_untested_tables` reports zero untested live tables.

## 11. Acceptance criteria / DoD
- [ ] 3 tables added to `EXPECTATIONS`; matrix green.
- [ ] `test_no_untested_tables` passes (no untested table).
- [ ] FORCE-RLS expectations reflect VC-P02.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P04 — Close the RLS test-matrix registry gap
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste rls pytest + no-untested-tables output · **EXCERPTS:** the added EXPECTATIONS rows · **QUESTIONS:** …
