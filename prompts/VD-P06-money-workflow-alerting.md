> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P06 — Money-workflow error alerting `[CODE]`

## 1. Context
**Wave 2 — SEQUENCE AFTER VD-P01** (shares `release-job.json` / `reconciliation.json`; not parallel-safe with VD-P01 on those files). Source: `01-audit-findings.md` §6 (workflow risks). **Risk:** the money workflows have **no error handling or failure alerting** — a failed/timed-out `httpRequest` (timeouts 30–120s) just errors the execution **silently**. A stalled Lenco reconciliation or escrow-release sweep would produce **no page**. Only `uptime-alert`/`admin-digest` have any alert path. Idempotency lives in the API, not the workflow, so a silent stall is invisible to ops.
**Type:** `[CODE]` — a coding agent adds error/retry/alert wiring to the money JSONs.

## 2. Objective & scope
Add retry + a founder-alert-on-failure path to the four money/ops-critical workflows so non-2xx money ticks page ops.
**Non-goals:** activating the workflows (VD-P01 does that first); changing the API handlers; the uptime webhook (VD-P05).

## 3. Files (edit ONLY these)
- `infra/n8n/release-job.json`, `infra/n8n/reconciliation.json`, `infra/n8n/payment-sweeper.json`, `infra/n8n/payout-failure-alert.json`
**Guardrail: modify ONLY these files, and ONLY after VD-P01 has set release-job's credential (rebase on its change to avoid clobbering).**

## 4. Implementation spec
- For each: add retry/backoff on the `httpRequest` node, and an **error path** (n8n `Error Trigger` / error-workflow, or an IF on non-2xx) that pages the founder (WhatsApp Cloud API, reusing the `admin-digest`/`uptime-alert` pattern) with the workflow name + status.
- Preserve existing schedules and endpoints (incl. `reconciliation`'s two triggers — the 30m poll **and** the daily `0 5 * * *` report). Keep tokens in credentials.
- Do not introduce money math in the workflow layer; alert payload is metadata only.

## 9. Security
- Tokens/secrets via credentials/env only. Alert payload contains no PII/payment refs — workflow name + HTTP status + timestamp only.

## 10. Tests (RUN before reporting)
- Force a non-2xx on each money tick (point at a failing/stub endpoint) → founder alert fires; success path unchanged.
- Retry/backoff observed in the execution log on a transient failure.
- `reconciliation` still fires both the 30m poll and the 05:00 daily report.

## 11. Acceptance criteria / DoD
- [ ] Each of the 4 money workflows pages the founder on non-2xx.
- [ ] Retry/backoff applied; schedules/endpoints unchanged (incl. recon dual trigger).
- [ ] No PII in alerts; no money math added to the workflow layer.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P06 — Money-workflow error alerting
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste forced-failure alert output + retry log (redacted)
**EXCERPTS:** the error/alert node wiring for one workflow
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
