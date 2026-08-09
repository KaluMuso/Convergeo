# INT-01 Combined Integration Certificate

**Status:** REHEARSAL ONLY — DO NOT MERGE THIS BRANCH TO MASTER  
**Generated:** 2026-08-09  
**Stack merge tip (last serial integration commit):** `601fc6cd8efa6d49e0e8a1747a7b0c5db2aa4b71`  
**Branch tip (includes this certificate):** see `cursor/int-rehearsal-stack-e9c5`  
**Base master:** `a57306d9e22067866af30341bf0e86f18bde4f74` (#603)

## Merge sequence (serial)

1. #604 QA-02 @ `3ad167ea82d31da5fb837ff633a82bbc78112d31`
2. #606 PAY-01 @ `99b5fa9a65efbb6a1e1cc07b936320e4c4cb899b`
3. #605 CUX-01 @ `2a44284003ee9b1432377f57e5eb90bfea2217be`
4. #607 Trust/Ops @ `1db2b70d0d19b14e0c4cb1d779475f3a055b6cb0`
5. #608 PDP/Trust @ `35bc91a1a0307a3487a6690fe3f4634c521346e8`
6. #609 Discovery @ `8215139fdeb8f181eac8db204072ca4b7fb1e842`

## Conflict outcomes (rehearsal)

| Hotspot                                           | Result                                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `packages/i18n/messages/*/catalog.json`           | Deep-merged bem/nya for reportListing (#607) + verifiedPurchase/conditionUsed (#608) |
| `services/api/app/core/ratelimit_policies.py`     | Auto-merged report + discovery policies                                              |
| PDP `page.tsx` / `comparison.tsx` / gallery tests | Auto-merged report UI + Modal/JSON-LD                                                |
| Customer layouts (#605)                           | No cross-PR conflict                                                                 |
| `main.py`                                         | No multi-PR conflict on this stack                                                   |

## Evidence

### Local (stack tip)

- QA self-tests: **18/18 pass**
- PAY-01 + discovery privacy/trending/kind-totals + listing reports: **52 passed**
- Money verdict: `CODE_MONEY_SAFE_FOR_STAGING_SANDBOX`

### GitHub required gates on branch tip `d004cc95` (PR #610)

All required workflow checks **SUCCESS** (JS/TS, Python API, RLS, authz, migration replay, typegen, money DB, COD smoke, dependency audit, secret scan, i18n, Performance budgets).  
Vercel preview deployments are rate-limited (`upgradeToPro=build-rate-limit`) — **BLOCKED_EXTERNAL**, non-blocking for code merge gates.

## Stale PR classification

| PR   | Classification                                   |
| ---- | ------------------------------------------------ |
| #600 | STALE docs-only audit draft — not in merge stack |
| #601 | SUPERSEDED by #607+#608+#609 — MUST NOT MERGE    |
| #602 | SUPERSEDED by #604 — MUST NOT MERGE              |

## Explicit non-actions

- Not merged to master
- Not deployed to production
- No production Supabase / Vercel / payments / n8n mutations
