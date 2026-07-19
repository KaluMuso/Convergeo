# Wave 2 — Dispatch Runbook (VM-B money verify · VM-D automations · VM-E obs setup)

**Date:** 2026-07-19 · **Plan:** D30 hybrid — **runs in parallel with Wave 1.** · **Prompts:** `prompts/VB-*`, `prompts/VD-P01…P06`, `prompts/VE-P01/P02`.
Wave 2 proves the money/escrow/KYC path and lights up the dormant automations — **all on the isolated sandbox target, never prod money.**

## Guardrails (do NOT)
- **Sandbox only.** `LENCO_ENV=sandbox`; `payments_enabled()` true **only** on the isolated stack; **0 production payments**. Do not flip `public_launch` / prepaid / `zamtel_collections`.
- Run money drills against the **throwaway DB branch + API from Wave 1** (VA-P02/VA-P03), not the live prod DB.
- Redact all PII / payment refs / Lenco tokens / n8n tokens in evidence — aggregates + redacted ids only.
- Keep `abandoned-cart` + `funnel-abandon` workflows **OFF** (flag-gated); don't enable Zamtel.

## Access needed
| System | For |
| ------ | --- |
| Lenco **sandbox** creds (F9b) | VB money drills |
| Isolated stack (Wave-1 DB branch + pinned API) | VB, VD |
| n8n instance + per-concern `INTERNAL_*` tokens | VD-P01…P06 |
| Sentry org `convergeo-w2` | VE-P01 |
| UptimeRobot | VE-P02 |

## Execution order (4 tracks; A gates parts of B)
```
Track A  MONEY (sequenced): VB-P01 MoMo → VB-P02 card → VB-P03 replay → VB-P04 release → VB-P05 refund → VB-P06 recon
Track B  AUTOMATIONS: VD-P04 backup ‖ VD-P05 uptime-auth ‖ VD-P03 lifecycle  (independent)
                      VD-P01 escrow-release  ← needs VB-P04    →  VD-P06 money-alerting (after VD-P01)
                      VD-P02 tickets         ← needs VB-P04
Track C  OBS: VE-P01 Sentry ‖ VE-P05→ VE-P02 uptime (needs VD-P05 webhook auth)
Track D  CODE (dispatch to Cursor): VB-P07 false-success E2E  (needs Wave-1 promoted FE + sandbox)
```
Start Track A; run Tracks B/C/D in parallel, honoring the two "needs VB-P04" edges and "VD-P06 after VD-P01".

---

## TRACK A — Money & escrow sandbox proof `[OPS]` · prompt `VB-P01-06`
Run the whole chain on one sandbox order. After each stage run `scripts/db/ledger-invariants.sql` (zero-sum + no orphan legs).
| # | Do | Verify | Evidence |
| - | -- | ------ | -------- |
| VB-P01 | Sandbox **MoMo** prepaid checkout | `CHARGE_RECEIVED` + escrow-hold legs; ledger nets 0; redacted Lenco match | `evidence/money-momo.md` |
| VB-P02 | Sandbox **card** (Lenco widget) | same invariants | `evidence/money-card.md` |
| VB-P03 | **Replay** the same webhook | single ledger txn (`webhook_events` unique / `23505`); bad sig → 401 | `evidence/webhook-idempotency.md` |
| VB-P04 | Escrow **release** tick | `COMMISSION_CAPTURE` **before** `RELEASE_TO_VENDOR`; escrow→0; double-tick captures once | `evidence/release-accounting.md` |
| VB-P05 | **Cancel + refund** | one `rfd-*` payout (stable idempotency key); lane-1/lane-2 math correct | `evidence/refund-matrix.md` |
| VB-P06 | Force a **recon mismatch** | actionable alert; `reconciliation_reports` row; no silent drift | `evidence/recon-alert.md` |

**Backstop tests:** `python load/invariant-check.py` (zero oversell / balance / gapless invoice) + `uv run pytest services/api/tests/test_ledger.py test_release_accounting.py test_refund_execute.py test_reconcile.py -q`.
**Exit:** S1–S3 + S6 evidence maps STAGING_VERIFIED. **No prod money.**

## TRACK B — Automations `[OPS]` / `[CODE]` · prompts `VD-P01…P06`
| Pebble | Type | Do | Verify |
| ------ | ---- | -- | ------ |
| VD-P01 | OPS | Activate `release-job` + `order-jobs` (`INTERNAL_RELEASE_JOB_TOKEN`/`_ORDER_JOBS_TOKEN`); chain **auto-confirm → auto-release** | authed tick 200; sandbox releases once; re-tick no double-release; unauth → 401 |
| VD-P02 | OPS | Activate `tickets-issue`/`tickets-release`/`event-release` | exactly-once ticket issue (60s tick); QR+PIN verify; no premature hold release |
| VD-P03 | OPS | Activate 8 lifecycle workflows (kyc-nudge, payout-failure, low-stock, review-request, reservation-sweeper, embeddings-cron, analytics-retention, admin-digest) | each ticks once; digest reaches founder WhatsApp; abandoned-cart/funnel stay OFF |
| VD-P04 | CODE+OPS | Author `infra/n8n/backup.json` (cron `0 2 * * *` Africa/Lusaka → `scripts/db-dump.sh`) + registry row; deploy | `test_n8n_registry.py` green; one dated dump; failure branch alerts |
| VD-P05 | CODE | Add shared-secret/HMAC (`UPTIME_WEBHOOK_SECRET`) to `/webhook/uptime-alert` | unauth POST rejected; correct-secret down-alert pages founder |
| VD-P06 | CODE | **(after VD-P01)** error/retry + founder alert on non-2xx for `release-job`/`reconciliation`/`payment-sweeper`/`payout-failure-alert` | forced 500 pages founder; schedules unchanged |
Evidence: `evidence/n8n-release.md`, `n8n-tickets.md`, `n8n-lifecycle.md`. **Exit:** G5 (release + tickets active/proven); backup workflow live.

## TRACK C — Observability `[OPS]` · prompts `VE-P01/P02`
| Pebble | Do | Verify | Evidence |
| ------ | -- | ------ | -------- |
| VE-P01 | Create Sentry projects (customer/vendor/admin/API) under `convergeo-w2`; set DSN envs | test error visible per app, correct release tag; no client-bundle regression | `evidence/sentry.md` |
| VE-P02 | UptimeRobot monitors on the 4 health endpoints; wire down-alert to VD-P05 webhook | monitors green; forced down → founder page; up → silent | `evidence/uptime.md` |

## TRACK D — False-success E2E `[CODE → dispatch to Cursor]` · prompt `VB-P07`
- Dispatch the `VB-P07` prompt to a Cursor agent (it's the one pure-code pebble). Owns `e2e/specs/checkout-false-success.spec.ts` (distinct from VE-P07).
- **Verify:** `pnpm e2e -g "false-success"` green on the sandbox stack — pending/failed MoMo never shows "paid"; COD ≤K500 never claims MoMo success.

---

## Report back (Phase-4 review)
Paste each pebble's **IMPLEMENTATION REPORT** (STATUS / FILES / DEVIATIONS / TESTS / EXCERPTS / QUESTIONS). I'll apply heightened scrutiny to the money/escrow/idempotency evidence, map the S1–S6 / G3/G4/G5 gates in `release-gates.md`, update `docs/plan/00-status.md`, and green-light Wave 3 (trust/security — `0056` prod rollout, FORCE RLS, role hook), which per the plan follows the money proof.

**Wave 2 exit:** money/escrow/refund/recon **STAGING_VERIFIED** on sandbox (S1–S6), escrow-release + ticket-issue + lifecycle workflows **active and proven**, backup workflow live, Sentry + uptime green. Still **no real money, `public_launch=false`** — that stays gated on Wave 3 + legal + the Go/No-Go pack (VE-P09).
