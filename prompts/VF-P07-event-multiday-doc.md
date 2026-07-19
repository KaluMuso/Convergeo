> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P07 — Event `multi_day` doc reconciliation `[DOC]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` BG-9; MR-S08; **FD-05 (NB-4)**. **Live:** the event-type CHECK is four types (`standard|recurring|free_rsvp|private`); the events-strategy docs mention a fifth `multi_day`. **Default (FD-05): accept `standard` + `ends_at`** — no enum churn before the money/n8n gates.
**Type:** `[DOC]`.

## 2. Objective & scope
Reconcile the docs/UI so multi-day events are described as `standard` + `ends_at`, not a distinct type.
**Non-goals:** any schema change (no `multi_day` enum unless FD-05 later elevates); UI type-picker additions.

## 3. Files (edit ONLY these)
- `docs/plan/00-decisions.md` (record the FD-05 resolution)
- `docs/plan/events-strategy-remediation.md` and/or events copy notes referencing the five-type claim
**Guardrail: docs only; do NOT add a CHECK value or a UI type.**

## 4. Implementation spec
- Record FD-05 = "accept `standard` + `ends_at`"; update the events docs so no artifact claims a distinct `multi_day` type.
- Note the elevation path (additive enum) if organisers later cannot describe multi-day events honestly with `ends_at`.

## 10. Tests / verification
- `grep -ri "multi_day" docs/` shows only the reconciled/"deferred" framing, not an active launch claim.

## 11. Acceptance criteria / DoD (FD-05/MR-S08)
- [ ] Docs/UI describe multi-day as `standard`+`ends_at`; no active `multi_day`-type claim.
- [ ] FD-05 recorded in `00-decisions.md`; no schema change.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P07 — Event `multi_day` doc reconciliation
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the `grep -ri multi_day docs/` result · **EXCERPTS:** none · **QUESTIONS:** …
