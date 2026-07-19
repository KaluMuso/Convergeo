> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P02 — Activate ticket issuance / release + event-release workflows `[OPS]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` DL-4 / §6; MR-W02; `release-gates.md` G5. **Depends on VB-P04** (release accounting) + VA-P03. **Live:** `tickets-issue.json`, `tickets-release.json`, `event-release.json` are committed `active:false`; routes exist (`internal_tickets.py`, `internal_event_release.py`) but never fire → **paid tickets would never issue** and event escrow never releases. `tickets-issue` ticks every 60s; `tickets-issue`+`tickets-release` share `INTERNAL_TICKETS_ISSUE_TOKEN`; `event-release` uses `INTERNAL_EVENT_RELEASE_TOKEN`.
**Type:** `[OPS]` — Cursor prepares import notes + evidence; the **founder** activates in n8n.

## 2. Objective & scope
Activate the three ticket/event workflows and prove exactly-once ticket issuance + dynamic-QR verification + event-escrow release on the sandbox stack.
**Non-goals:** escrow order-release (VD-P01); lifecycle nudges (VD-P03); enabling paid events in production.

## 3. Files (create / edit ONLY these)
- `infra/n8n/tickets-issue.json`, `infra/n8n/tickets-release.json`, `infra/n8n/event-release.json` (swap `REPLACE_WITH_CREDENTIAL_ID`)
- `…/vision-audit/evidence/n8n-tickets.md`
**Guardrail: do NOT touch other `infra/n8n/*.json`.**

## 4. Implementation spec
- Import + `active:true`; bind `INTERNAL_TICKETS_ISSUE_TOKEN` (issue+release) and `INTERNAL_EVENT_RELEASE_TOKEN` (event-release).
- Prove on a sandbox paid ticket order: `tickets-issue` tick issues **exactly one** ticket per paid line (server-side idempotency in `internal_tickets` — confirm no double-issue at the 60s cadence under overlap); the ticket wallet shows a rotating 60s-HMAC QR + 6-digit PIN that **verifies** (`ticket_verify`); `tickets-release` frees only genuinely-stale holds (no premature release → no oversell); `event-release` releases the event-escrow phase on schedule.

## 9. Security
- Shared/distinct tokens in n8n credentials only; `X-Internal-Token` required (401 without). QR secret never leaves the server (window-sigs only).

## 10. Tests / verification (RUN before reporting)
- Issue tick → exactly one ticket for one paid line; re-tick issues none more.
- QR + PIN verify via `ticket_verify`; a tampered/expired QR is rejected.
- `tickets-release` does not free a not-yet-expired hold (oversell guard).
- Unauthenticated internal POST → 401. Execution ids recorded.

## 11. Acceptance criteria / DoD (maps to G5 / MR-W02)
- [ ] Three workflows active with correct tokens.
- [ ] Exactly-once ticket issuance on sandbox; dynamic-QR + PIN verify.
- [ ] No premature ticket-hold release; event-escrow releases on schedule.
- [ ] Execution ids in `n8n-tickets.md`; no production money.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P02 — Activate ticket issuance / release + event-release
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste issue/verify/release tick output + execution ids (redacted)
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
