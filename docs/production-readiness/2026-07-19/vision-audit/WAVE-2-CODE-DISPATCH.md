# Wave 2 — CODE pebble dispatch (Cursor)

**Date:** 2026-07-19 · Prep verified against `master` (all referenced files/paths confirmed present or correctly-absent). Four `[CODE]`/`[CODE+OPS]` pebbles for Cursor Composer; the `[OPS]` pebbles (VD-P01/P02/P03) and the live drills stay with the founder.

## How to dispatch each pebble (Composer agents share no memory)
1. **Prepend `prompts/_header.md`** (PROJECT HEADER) above the pebble prompt — required context.
2. Paste the pebble prompt (path in the table). One pebble = one branch = one PR.
3. Branch `cursor/<slug>`; PR title = the pebble id (e.g. `VB-P07: checkout false-success E2E`).
4. Agent runs the prompt's §10 tests and returns the §12 IMPLEMENTATION REPORT. Paste each report back here — I review (heightened scrutiny on the money/webhook wiring) before merge.

## Batch 1 — dispatch in PARALLEL now (file-disjoint, no code cross-deps)

| Pebble | Prompt | Exclusive files (owns) | Verify (§10) |
| ------ | ------ | ---------------------- | ------------ |
| **VB-P07** false-success E2E | `prompts/VB-P07-false-success-e2e.md` | `e2e/specs/checkout-false-success.spec.ts` (+ `e2e/fixtures/lenco-sandbox.ts` only if needed) | `pnpm --filter e2e test -g "false-success"` — pending/COD assertions run **credential-free**; Lenco-gated steps `test.skip()` without creds |
| **VD-P04** DB backup workflow `[CODE+OPS]` | `prompts/VD-P04-backup-workflow.md` | `infra/n8n/backup.json` (new), `scripts/db-dump.sh` (new), `docs/ops/n8n-workflows.md` | `bash -n` + `shellcheck` on the script; `uv run pytest services/api/tests/test_n8n_registry.py -q`; local dump round-trip |
| **VD-P05** uptime webhook HMAC `[CODE]` | `prompts/VD-P05-uptime-webhook-auth.md` | `infra/n8n/uptime-alert.json`, `docs/ops/observability.md` | unauth POST → no WhatsApp send; correct-secret `alertType:1` → page; `alertType:2` → no page |

**Parallel-safety proven** — no file is touched by more than one Batch-1 pebble, and none is touched by the pending `[OPS]` pebbles either:
- VD-P03 guardrail explicitly excludes `uptime-alert.json` and `backup.json`; VD-P01/P02 own only `release-job`/`order-jobs`/`tickets-*`/`event-release`. `docs/ops/n8n-workflows.md` is VD-P04's alone (OPS pebbles write their own `n8n-*.md` evidence docs).
- VB-P07's `checkout-false-success.spec.ts` is a new file, distinct from VE-P07's `critical-path.spec.ts`.

**Ship state:** VD-P04/P05 JSONs ship `active:false` with credential placeholders — the founder activates + sets secrets afterward (VD-P04 deploy/one-dump; VD-P05 secret + point UptimeRobot, VE-P02). VB-P07 depends on VA-P01 (frontends promoted — **done**); full green needs the sandbox stack, but the credential-free assertions pass in CI now.

## Batch 2 — dispatch AFTER the OPS credential swaps

| Pebble | Prompt | Files | Gated on |
| ------ | ------ | ----- | -------- |
| **VD-P06** money-workflow alerting `[CODE]` | `prompts/VD-P06-money-workflow-alerting.md` | `infra/n8n/release-job.json`, `reconciliation.json`, `payment-sweeper.json`, `payout-failure-alert.json` | **VD-P01** (owns `release-job.json`) **and VD-P03** (owns `payout-failure-alert.json`) — both swap `REPLACE_WITH_CREDENTIAL_ID`. Dispatch VD-P06 only after those land, and rebase on them (prompt now states both deps). `reconciliation.json` + `payment-sweeper.json` are VD-P06-exclusive. |

Verify (§10): force a non-2xx on each money tick → founder alert; retry/backoff in the execution log; `reconciliation` still fires both the 30m poll and the `0 5 * * *` daily report.

## `infra/.env.example` — keep out of Cursor scope
VD-P04 (OCI/rclone dump env) and VD-P05 (`UPTIME_WEBHOOK_SECRET`) introduce new env names. To keep the pebbles file-disjoint, **each documents its env name in its own doc** (VD-P04 → `n8n-workflows.md`, VD-P05 → `observability.md`) and references it via `$env.*` only. The founder adds the names to `infra/.env.example` at activation time — no Cursor agent edits `.env.example` (it's a shared file + the JSONs ship `active:false` anyway).

## Full Wave-2 n8n file-ownership map (reference)
| File | Owner |
| ---- | ----- |
| `release-job.json` | VD-P01 (cred) → then VD-P06 (alerting) |
| `order-jobs.json` | VD-P01 |
| `tickets-issue/tickets-release/event-release.json` | VD-P02 |
| `kyc-nudge/low-stock-alert/review-request/reservation-sweeper/embeddings-cron/analytics-retention/admin-digest.json` | VD-P03 |
| `payout-failure-alert.json` | VD-P03 (cred) → then VD-P06 (alerting) |
| `reconciliation.json`, `payment-sweeper.json` | VD-P06 |
| `backup.json` (new) | VD-P04 |
| `uptime-alert.json` | VD-P05 |
| `abandoned-cart.json`, `funnel-abandon.json` | **stay OFF** (flag-gated) — nobody activates |

## After dispatch
Paste each IMPLEMENTATION REPORT here. I apply the Phase-4 review (money/webhook wiring, secret handling, no-PII-in-alerts, schedules preserved), then the founder does the per-pebble OPS activation. Wave-2 exit still gates on the founder's live Lenco walk (S1–S6) + obs — see `WAVE-2-DISPATCH.md` and `evidence/wave2-code-readiness-rollup.md`.
