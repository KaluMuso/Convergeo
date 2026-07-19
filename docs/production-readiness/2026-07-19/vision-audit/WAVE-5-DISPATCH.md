# Wave 5 — Dispatch Runbook (VM-F · Vision Build Gaps)

**Date:** 2026-07-19 · **Gate on entry:** money/trust path proven (Waves 2–4). · **Prompts:** `prompts/VF-P01…P07`.
Wave 5 closes the genuine build gaps left after the audit. **Every pebble is `[CODE]` or `[DOC]` — dispatch each as a Cursor agent** (no privileged OPS). Parallel-safe on disjoint files except the three sequencing edges noted below. **The M17 video feed stays deferred by design — not in this wave.**

## Guardrails (do NOT)
- Bemba/Nyanja strings must be **human-reviewed**, not machine-dumped; keys must mirror `en/` exactly (no key drift).
- **No invented admin roles** — VF-P03 is docs per D33 (single `admin`).
- VF-P06 is **money-adjacent**: integer ngwee only, config-driven cap, guarded + audited, failure-path test required.
- Do **not** add `product_class`/used-goods (D34 keeps that OUT); do **not** build the video feed (M17, post-launch).

## Dispatch table (each = one Cursor branch/PR `VM-F-Pnn`)
| Pebble | Type | Owns | Do | Verify | Sequencing |
| ------ | ---- | ---- | -- | ------ | ---------- |
| VF-P01 | CODE | `packages/i18n/messages/bem/*`, `…/nya/*` | fill 16 namespaces each (human-reviewed, ICU-valid), keys mirroring `en/` | `node scripts/ci/i18n-lint.mjs` clean (no missing/extra keys); core flows render vernacular | — |
| VF-P02 | CODE | `packages/i18n/src/locales.ts` + locale-switcher component | add `PUBLIC_LOCALES` (en, fr, bem, nya); drop `zh` from the **public** switcher (keep it routable for QA) | switcher omits `zh`; `/zh/...` still 200; typecheck green | **after VF-P01** |
| VF-P03 | DOC | `docs/ops/admin-access.md` | per D33: document guarded single-`admin` grant/revoke + Access; no CRUD UI, no new roles | runbook copy-pasteable; matches DB CHECK | follows VC-P07 |
| VF-P04 | CODE | `services/api/app/routers/search.py`, `…/services/embeddings/*` | diagnose + fix `/search` `degraded=true` (embeddings backlog / FTS / RRF lane) | representative queries `degraded=false`; `uv run pytest services/api/tests/test_search*.py -q` green | **after VC-P06** (shared `search.py`) |
| VF-P05 | CODE | `apps/vendor/sw-scanner.ts` + scan components | cache tickets for offline verify; queue scans; sync + first-scan-wins | offline verify works; reconnect syncs; duplicate loses to first; secret never client-side | — |
| VF-P06 | CODE | `services/api/app/services/events/*` + `tests/test_event_*.py` | enforce Tier-1 organiser GMV cap before paid-ticket escrow; over-cap → reject/hold + audit | over-cap Tier-1 rejected+audited; under-cap ok; Tier-2 unaffected; failure-path test green | — |
| VF-P07 | DOC | `docs/plan/00-decisions.md` + events copy | record FD-05: `multi_day` = `standard`+`ends_at`; align copy; no enum/schema change | `grep -ri multi_day docs/` shows only the reconciled framing | — |

## Report back (Phase-4 review)
Paste each pebble's **IMPLEMENTATION REPORT**. Heightened scrutiny on **VF-P06** (money cap: integer ngwee, guarded, failure-path). I'll confirm no i18n key drift (VF-P01), no invented roles (VF-P03), and that VF-P04 fixes the root cause (not just suppresses the flag). Maps **BG-1/2/3/4, MR-B04/B07/V03, FD-05, NB-1**.

**Wave 5 exit:** Bemba/Nyanja core flows translated, `zh` de-routed from the public switcher, admin user-mgmt documented, `/search` healthy, offline scanner robust, organiser GMV cap enforced, `multi_day` reconciled. This clears the **P1/P2 build gaps** — orthogonal to the launch-gating money/trust waves. Video feed (M17) remains a separate post-launch v2 track.
