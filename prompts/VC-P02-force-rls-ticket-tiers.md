> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P02 — FORCE RLS on ticket-tier + product_relations `[CODE]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §5; MR-R01; **FD-07 (B-3)**; `release-gates.md` G0. **Live:** `relforcerowsecurity = false` on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations` while most money/PII tables force RLS — a real-money isolation gap for paid events. **Requires B-3 = "enable" (default).**
**Type:** `[CODE]` — additive migration; **sole editor of the new migration file only** (test-matrix edits belong to VC-P04 to keep ownership exclusive within the wave).

## 2. Objective & scope
Additive migration enabling FORCE RLS on the three tables, fixing any table-owner/service-role assumption that FORCE would break.
**Non-goals:** editing `tests/rls/test_matrix.py` (VC-P04 owns it — coordinate the FORCE expectation there); the role hook (VC-P03).

## 3. Files (create ONLY these)
- `supabase/migrations/00NN_force_rls_ticket_tiers.sql` — **number above master's current max prefix and land promptly** (per `00-status.md` duplicate-prefix hazard; the CI guard in `scripts/ci/migration-replay.sh` will catch a collision)
**Guardrail: do NOT edit existing migrations or test files.**

## 4. Implementation spec
- `ALTER TABLE … FORCE ROW LEVEL SECURITY` on the three tables.
- Verify service-role/internal ticket paths (`internal_tickets`, inventory claim) still function under FORCE (service role bypasses RLS; a table **owner** does not — fix any owner-context assumption).
- Re-run `get_advisors(security)` mentally against the change: no new "RLS disabled/forced-false" finding.

## 9. Security
- Additive-only, reversible; no policy loosened. Money isolation strengthened.

## 10. Tests (RUN before reporting)
- `supabase db reset` applies the migration cleanly; `scripts/ci/migration-replay.sh` (duplicate-prefix guard) green.
- `uv run pytest services/api/tests/rls -q` green (VC-P04 adds the FORCE assertions; this pebble must not regress existing RLS tests).
- Ticket purchase/claim path still works locally (no service-role break).

## 11. Acceptance criteria / DoD (G0)
- [ ] FORCE RLS true on the 3 tables via additive migration (unique prefix).
- [ ] Advisor clean; no service-role/inventory regression.
- [ ] Existing RLS suite green.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P02 — FORCE RLS on ticket-tier + product_relations
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste db reset + migration-replay + rls pytest · **EXCERPTS:** the migration SQL · **QUESTIONS:** …
