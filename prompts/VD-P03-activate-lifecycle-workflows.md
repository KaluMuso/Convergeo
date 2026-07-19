> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P03 — Activate lifecycle workflows `[OPS]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` §6; MR-W03/W06. **Depends on Wave 1** (API pinned). **Live:** only dispatch + reconciliation are active. The lifecycle/ops workflows are committed `active:false`; their `/internal/*` routes exist (`internal_n8n.py`, `internal_stock_sweeper.py`, `internal_embeddings.py`, `internal_analytics.py`, `internal_digest.py`, `internal_funnel.py`).
**Type:** `[OPS]` — Cursor prepares import notes + evidence; the **founder** activates in n8n.

## 2. Objective & scope
Activate the non-money lifecycle workflows and prove each ticks once; keep the two flag-gated ones inert.
**Non-goals:** money/ticket workflows (VD-P01/P02); the backup workflow (VD-P04); error alerting (VD-P06).

## 3. Files (edit / create ONLY these)
- `infra/n8n/kyc-nudge.json`, `payout-failure-alert.json`, `low-stock-alert.json`, `review-request.json`, `reservation-sweeper.json`, `embeddings-cron.json`, `analytics-retention.json`, `admin-digest.json` (swap credential id)
- `…/vision-audit/evidence/n8n-lifecycle.md`
**Guardrail: leave `abandoned-cart.json` + `funnel-abandon.json` OFF (flag-gated by `feature_flags.abandoned_cart`); do NOT touch money/ticket/backup/uptime JSONs.**

## 4. Implementation spec
- Import + `active:true` for the 8 above; bind the correct token per workflow (`INTERNAL_N8N_TOKEN` shared by kyc-nudge/payout-failure/low-stock/review-request; `INTERNAL_STOCK_SWEEPER_TOKEN`; `INTERNAL_EMBEDDINGS_TOKEN`; `INTERNAL_ANALYTICS_TOKEN`; `INTERNAL_DIGEST_TOKEN`).
- Prove each ticks once (200 authed); `admin-digest` reaches the founder WhatsApp (display-only, `gmv_ngwee/100` formatting stays display-only — never writes back); `embeddings-cron` drains pending jobs; `analytics-retention` NULLs person-links > 30d.
- Confirm `abandoned-cart` + `funnel-abandon` remain inert while `abandoned_cart=false`.

## 9. Security
- Tokens in n8n credentials only; `X-Internal-Token` required (401 without). `analytics-retention` operates service-role, idempotent. No PII in the evidence doc.

## 10. Tests / verification (RUN before reporting)
- Each workflow: one authenticated tick → 200; execution id recorded.
- `admin-digest` delivers to founder WhatsApp (redacted).
- Flag-gated pair confirmed inert (no outbox rows enqueued).

## 11. Acceptance criteria / DoD (maps to MR-W03/W06)
- [ ] 8 lifecycle workflows active with correct tokens; each ticks once.
- [ ] `abandoned-cart`/`funnel-abandon` remain OFF.
- [ ] Execution ids recorded; no money workflow touched here.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P03 — Activate lifecycle workflows
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste per-workflow tick output + execution ids (redacted)
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
