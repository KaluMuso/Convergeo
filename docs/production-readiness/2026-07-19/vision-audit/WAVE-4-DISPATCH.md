# Wave 4 — Dispatch Runbook (VM-E · Observability, Ops & Launch QA)

**Date:** 2026-07-19 · **Gate on entry:** Wave 2 (backup workflow VD-P04 live) + Wave 3 (trust/security). · **Prompts:** `prompts/VE-P03…P09`.
Wave 4 hardens ops and assembles the evidence that decides whether real-money beta is reachable. **VE-P09 is the terminal Go/No-Go step and must be filled from real evidence, never CODE_COMPLETE assumptions.**

## Guardrails (do NOT)
- Do **not** flip `public_launch` / money flags from any pebble here — that decision lives **only** in a separate change-controlled window **if** VE-P09 says GO (NB-13).
- Restore/rollback drills run against **scratch/dry-run targets**, never destructive on prod.
- No PASS from CODE_COMPLETE alone — every gate row needs VERIFIED evidence at the required maturity.

## Access needed
| System | For |
| ------ | --- |
| Backup artifact + scratch DB (from VD-P04) | VE-P03 restore drill |
| Vercel + API host | VE-P05 rollback drill |
| GitHub branch-protection UI | VE-P04 (confirm required checks) |
| Cursor agents | VE-P04/P06/P07 (CODE) |
| All Wave 1–4 evidence docs | VE-P09 Go/No-Go assembly |

## Execution order (3 tracks; C is last)
```
Track A  CODE (dispatch to Cursor, disjoint files): VE-P04 ci.yml ‖ VE-P06 perf.yml/lighthouserc ‖ VE-P07 e2e/critical-path
Track B  OPS drills: VE-P03 restore (needs VD-P04) ‖ VE-P05 rollback ‖ VE-P08 env-isolation plan
Track C  VE-P09 Go/No-Go pack  ← LAST: assembles Waves 1–4 evidence
```

---

## TRACK A — CODE `[CODE → dispatch to Cursor]` (disjoint files, parallel-safe)
| Pebble | Owns | Do | Verify |
| ------ | ---- | -- | ------ |
| VE-P04 | `.github/workflows/ci.yml`, `docs/ops/ci.md` | remove `continue-on-error:true` from `secret-scan`; reconcile ci.md; founder confirms branch protection requires it | a planted secret **fails** CI; clean commit passes; ci.md matches YAML |
| VE-P06 | `.github/workflows/perf.yml`, `lighthouserc.json` | make Lighthouse/budget assertions enforcing (drop advisory); re-probe customer routes at 360px/Fast-3G | over-budget route **fails**; baseline passes; Perf≥90/SEO≥95/A11y≥95, ≤150KB gz, LCP≤2.5s (or documented per-route waiver) |
| VE-P07 | `e2e/specs/critical-path.spec.ts` (distinct from VB-P07) | happy-path browse→cart→sandbox checkout→confirm at 360px/Fast-3G | `pnpm e2e -g "critical-path"` green on the sandbox stack |

## TRACK B — Ops drills `[OPS]`
| Pebble | Do | Verify | Evidence |
| ------ | -- | ------ | -------- |
| VE-P03 | Restore VD-P04's dump into a **scratch** DB | integrity/key invariants match source; RPO/RTO documented vs DR runbook | `evidence/restore-drill.md` |
| VE-P05 | Dry-run rollback: promote a prior Vercel prod deploy + roll the API image back one tag, then roll forward | both served a prior version then returned to tip; health 200 throughout; times recorded | `evidence/rollback-drill.md` |
| VE-P08 | Document (and schedule) moving Vergeo5 API/n8n off the shared WAHA/ZedApply VM; confirm the WhatsApp Cloud-API sender number is separate from any WAHA sender (NB-7) | isolation plan with owner+date+cost; number-separation confirmed | `evidence/env-isolation-plan.md` |

## TRACK C — Go / No-Go `[OPS]` · **LAST**
| Pebble | Do | Verify | Evidence |
| ------ | -- | ------ | -------- |
| VE-P09 | Fill the `release-gates.md` release-evidence template from Waves 1–4: frontend SHAs, API digest, DB migration head (incl `0056`), active n8n workflows, Sentry projects, uptime monitors, backup+restore, sandbox payment proofs (redacted), RLS probe, KYC orphan count, CI run, rollback drill, legal sign-off, flags | every S0–S7 / G0–G22 row = PASS/FAIL with an evidence pointer; per-area maturity recorded; **no PASS from CODE_COMPLETE alone**; Go/No-Go decision stated | `evidence/go-no-go-YYYYMMDD.md` |

---

## Report back (Phase-4 review)
Paste each pebble's **IMPLEMENTATION REPORT**. I'll confirm the CI/perf gates are genuinely enforcing (not advisory), the restore/rollback drills produced real timings, and — critically — that **VE-P09 maps every gate honestly**. Maps **G6/G7/G8/G9/G16/G19** + the Go/No-Go table.

**Wave 4 exit:** blocking CI security gates, proven backup **and** restore, timed rollback, enforced perf budgets, critical-path E2E green, environment-isolation plan, and a **filled Go/No-Go pack**. Only if that pack says GO — plus Wave 3 legal (G13) — does real-money beta become a separate, change-controlled decision. `public_launch=false` until then.
