> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P05 — Authenticate the uptime-alert webhook `[CODE]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` §6 (workflow risks). **Risk:** `infra/n8n/uptime-alert.json` exposes an **unauthenticated** `n8n-nodes-base.webhook` at `POST /webhook/uptime-alert` (`responseMode: onReceived`, no shared-secret/HMAC). Anyone who discovers the path can POST `{alertType:"1"}` and **page the founder's WhatsApp** (spam / alert-fatigue / phishing vector). It calls the WhatsApp Cloud API directly with template `ops_uptime_alert`.
**Type:** `[CODE]` — a coding agent hardens the workflow (and, if needed, documents the UptimeRobot config).

## 2. Objective & scope
Require a shared secret on the uptime webhook so only UptimeRobot can trigger the founder page.
**Non-goals:** activating monitors (VE-P02); other workflows; changing the WhatsApp template.

## 3. Files (edit ONLY these)
- `infra/n8n/uptime-alert.json`
- `docs/ops/observability.md` (note the secret header + UptimeRobot config — append only)
**Guardrail: modify ONLY these files.**

## 4. Implementation spec
- Add auth to the webhook node: either n8n Header-Auth on the webhook (a secret header UptimeRobot sends) **or** an early IF node that compares a `X-Uptime-Secret` header / query token against `$env.UPTIME_WEBHOOK_SECRET` and **short-circuits (no-op / 401)** when it doesn't match — before any WhatsApp call.
- Keep the down-only gate (`alertType == 1`) and the existing WhatsApp template path. Ship with `active:false` + placeholder; the founder sets the secret and points UptimeRobot at the authed URL (VE-P02).

## 9. Security
- Secret via `$env.UPTIME_WEBHOOK_SECRET` only, never in the JSON. Unauthenticated/incorrect-secret POST must **not** reach the WhatsApp node. Use constant-time comparison where the node allows.

## 10. Tests (RUN before reporting)
- `POST /webhook/uptime-alert` **without** the secret → rejected (no WhatsApp send).
- `POST` **with** the correct secret + `alertType:1` → founder page fires (sandbox/redacted).
- `alertType:2` (up) with valid secret → no page (down-only gate intact).

## 11. Acceptance criteria / DoD
- [ ] Unauthenticated POST cannot page the founder.
- [ ] Correct-secret down-alert still pages; up-alert does not.
- [ ] Secret via env only; `observability.md` documents the UptimeRobot header.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P05 — Authenticate the uptime-alert webhook
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the authed/unauthed webhook responses (redacted)
**EXCERPTS:** the auth/short-circuit node change
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
