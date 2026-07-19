> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P02 — Uptime monitors `[OPS]`

## 1. Context
**Wave 2 (observability).** Source: `01-audit-findings.md` X-1; MR-O02; `release-gates.md` G6. **Live:** uptime monitoring is NOT_AUDITABLE — no monitors probed. Pairs with **VD-P05** (the uptime-alert webhook must be secret-authed **before** UptimeRobot points at it).
**Type:** `[OPS]` — Cursor writes the evidence doc; the **founder** configures UptimeRobot.

## 2. Objective & scope
Stand up health monitors for all four surfaces and wire down-alerts to the (authed) founder-page webhook.
**Non-goals:** Sentry (VE-P01); authoring the webhook (VD-P05).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/uptime.md`
**Guardrail: secret + monitor config live in UptimeRobot/env, not repo.**

## 4. Implementation spec
- Monitors: `https://www.vergeo5.com/en/health`, `https://api.vergeo5.com/healthz`, `https://vendor.vergeo5.com/en/health`, `https://admin.vergeo5.com/en/health` (expect its Access challenge as "up").
- Point the down-alert at `POST /webhook/uptime-alert` with the `UPTIME_WEBHOOK_SECRET` header (from VD-P05); verify a forced down-alert pages the founder and an up-alert does not.

## 9. Security
- Webhook secret via env only; no monitor credentials in the evidence doc.

## 10. Tests / verification (RUN before reporting)
- All monitors green; a simulated/forced down → founder page fires (redacted); recovery clears.

## 11. Acceptance criteria / DoD (G6)
- [ ] 4 monitors green.
- [ ] Down-alert pages founder via the authed webhook; up-alert silent.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P02 — Uptime monitors
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste monitor states + down-alert proof (redacted) · **EXCERPTS:** none · **QUESTIONS:** …
