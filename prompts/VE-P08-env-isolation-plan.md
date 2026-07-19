> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P08 — Environment isolation plan `[OPS]`

## 1. Context
**Wave 4.** Source: `01-audit-findings.md` §8.1 X-9/X-10; **NB-7/NB-8** (Google Drive infra scan). **Finding:** the same `n8n-vnic-vergeo5` OCI VM appears to host **Vergeo5 (api/caddy/n8n) + WAHA + the separate ZedApply `zedcv-backend`** (a prior OOM incident on that box is documented in `docs/plan/00-status.md`). Two risks: (a) noisy-neighbor/blast-radius contention vs the $50/mo single-VM plan; (b) a WhatsApp **ban on the shared brand/number** would contaminate Vergeo5's official Cloud-API notifications — even though the Vergeo5 app code is WAHA-clean.
**Type:** `[OPS]` — a planning/decision doc (optionally executed later).

## 2. Objective & scope
Produce an isolation plan: separate Vergeo5's API/n8n from the shared WAHA/ZedApply workloads, and confirm the WhatsApp Cloud-API sender number is distinct from any WAHA sender.
**Non-goals:** the app-code WhatsApp path (already Cloud-API-only); executing the migration (this pebble plans; execution can follow).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/env-isolation-plan.md`
**Guardrail: no live infra teardown in this pebble; plan + confirm only.**

## 4. Implementation spec
- Inventory what runs on the VM (Vergeo5 api/n8n, WAHA, `zedcv-backend`) and its resource envelope; note the documented OOM history.
- Propose isolation: separate compartment/host (or move Vergeo5 API+n8n before real-money load), with owner + target date and a cost note vs the $50/mo ceiling.
- **Confirm the WhatsApp Cloud-API `phone_number_id` used by Vergeo5 is a different number from any WAHA sender on `waha.vergeo.company`** (NB-7) — record the finding.

## 10. Tests / verification
- N/A (plan). Include the current VM workload inventory + the WhatsApp number-separation confirmation as evidence.

## 11. Acceptance criteria / DoD (X-9, NB-7/8)
- [ ] Isolation plan with owner + date + cost note.
- [ ] WhatsApp sender number-separation confirmed (or flagged as a blocker if shared).

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P08 — Environment isolation plan
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** N/A · **EXCERPTS:** none · **QUESTIONS:** number-separation result
