> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P09 — Go / No-Go evidence pack `[OPS]`

## 1. Context
**Wave 4 (final gate).** Source: `../2026-07-18/consolidated/release-gates.md` (release-evidence template + Go/No-Go table). **Depends on Waves 1–4.** This is the assembly step that decides whether real-money beta is reachable — it must be filled from **actual evidence**, never from CODE_COMPLETE assumptions.
**Type:** `[OPS]` — Cursor assembles the pack from the evidence docs; the founder signs off.

## 2. Objective & scope
Fill the `release-gates.md` release-evidence template from the Wave 1–4 outputs and record per-area maturity + every S/G gate result.
**Non-goals:** flipping `public_launch` / money flags (that is a separate change-controlled window, only if the pack says GO — NB-13).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/go-no-go-YYYYMMDD.md`
**Guardrail: do NOT flip any feature flag from this pebble.**

## 4. Implementation spec
- Populate the release-evidence template: frontend SHAs, API image digest, DB migration head (incl `0056`), active n8n workflows, Sentry projects, uptime monitors, backup artifact + restore drill, sandbox payment proofs (MoMo/card/release redacted), RLS probe, KYC `0056`/orphan count, CI run, rollback drill, legal sign-off, flags.
- Record per-area maturity (CODE_COMPLETE / STAGING_VERIFIED / PRODUCTION_VERIFIED) and each S0–S7 / G0–G22 as PASS/FAIL with an evidence pointer.
- Apply the Go/No-Go table; state the decision. **No PASS from CODE_COMPLETE alone.**

## 10. Tests / verification
- Every gate row has a PASS/FAIL + evidence pointer; no blank/assumed cells; maturity labels honest.

## 11. Acceptance criteria / DoD
- [ ] Release-evidence template fully populated from real artifacts.
- [ ] S/G gates each PASS/FAIL with pointer; maturity per area recorded.
- [ ] Go/No-Go decision stated; no flag flipped.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P09 — Go / No-Go evidence pack
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** N/A (assembly) · **EXCERPTS:** the gate scoreboard · **QUESTIONS:** any gate lacking evidence
