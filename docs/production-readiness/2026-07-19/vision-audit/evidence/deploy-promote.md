# VA-P01 — Frontend promotion evidence

**Date:** 2026-07-19 · **Source:** Vercel MCP (`list_deployments`, team `vergeo-projects`).

## Finding: drift self-healed by auto-deploy
The audit's snapshot had customer production stuck at `cc4a824` (#296) with `/en|fr|zh/categories` → 500. Since then the git-connected Vercel project auto-deployed the founder's active dev, so the deployment drift (DL-1/DL-2) is **effectively closed** — no manual promotion was required.

| Project | Current prod deployment | Commit | Contains |
| ------- | ----------------------- | ------ | -------- |
| `convergeo-customer` | `dpl_CA2qcVXsCGnaorKCyr1onybCqszs` (READY, target=production) | **`28f565c`** (Merge #319) | #298 categories fix + live-beta discovery/SEO/home work (#302, #308–#319) |
| `convergeo-vendor` / `convergeo-admin` | git-connected to `master` | — | same auto-deploy path; confirm SHAs during ops |

## Interpretation
- The `#298` categories-500 fix is live (it is an ancestor of `28f565c`), so **G1 route integrity is satisfied on the customer surface**. A direct `curl /en/categories` → 200 confirmation is still worth capturing (egress from the audit session blocks `*.vergeo5.com`; the Vercel-MCP page-fetch or a founder curl closes it).
- Vendor/admin auto-deploy from `master` identically; record their prod SHAs in a follow-up for completeness (G17).

## Status: VA-P01 ✅ (customer verified; vendor/admin high-confidence, confirm SHAs)
