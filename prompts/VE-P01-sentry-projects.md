> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P01 — Sentry projects + DSNs `[OPS]`

## 1. Context
**Wave 2 (observability).** Source: `01-audit-findings.md` X-1/DL-7; MR-O01; `release-gates.md` G6. **Live:** Sentry org `convergeo-w2` has **no Vergeo5 projects** (only unrelated `zed*`). The app/API Sentry init exists (`services/api/app/core/sentry.py`, `apps/*/sentry.client.config.ts`) but is a **no-op without DSNs** — so production errors/money failures go unseen. (Note the M16-P06 bundle constraint: client Sentry is errors-only + lazy-loaded to protect the ≤150KB budget — do not re-enable Replay/tracing.)
**Type:** `[OPS]` — Cursor writes the evidence doc; the **founder** creates projects + sets DSN envs.

## 2. Objective & scope
Create Vergeo5 Sentry projects and wire DSNs so each surface reports errors.
**Non-goals:** uptime monitors (VE-P02); code changes to the (correct) Sentry init; re-adding Session Replay/browser-tracing.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/sentry.md`
**Guardrail: DSNs go in Vercel/host env, never in repo.**

## 4. Implementation spec
- Create projects (customer / vendor / admin / API) under `convergeo-w2`.
- Set `NEXT_PUBLIC_SENTRY_DSN` per app on Vercel + `SENTRY_DSN` on the API host; set `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`/`NEXT_PUBLIC_SENTRY_RELEASE` to the deployed SHAs.
- Trigger a test error per surface; confirm it lands with the right release tag.

## 9. Security
- PII scrubber stays enabled (per `sentry.py`); no secrets in the evidence doc; DSNs are env-only.

## 10. Tests / verification (RUN before reporting)
- One test error visible in each of the 4 projects, tagged with the deployed release.
- Customer bundle unchanged (no Replay/tracing regression).

## 11. Acceptance criteria / DoD (G6)
- [ ] 4 Vergeo5 Sentry projects exist; DSNs set per surface.
- [ ] Test error ingested per app with correct release tag.
- [ ] No client-bundle regression.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P01 — Sentry projects + DSNs
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description · **DEVIATIONS:** … · **TESTS:** paste per-project test-event links (redacted) · **EXCERPTS:** none · **QUESTIONS:** …
