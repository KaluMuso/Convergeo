# Customer `/categories` post-deploy check — PR #298

**Role:** Read-only production verification  
**Session:** `https://cursor.com/agents/bc-b132b770-f76c-46da-b328-2c79c4f4435a`  
**UTC window:** 2026-07-19T01:48–01:50Z  
**Mode:** Evidence only — no code, database, env, DNS, Vercel config, or deployment changes

**Verdict: FAIL** — all three locale routes return HTTP 500 with the pre-fix client-boundary error. Production is still on commit `cc4a824…` (PR #296); PR #298 (`b17c311…`) is merged to `master` but **not** deployed to the customer production aliases.

---

## 1. PR #298 vs production deployment

| Item                              | Value                                                                                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PR                                | [#298](https://github.com/KaluMuso/Convergeo/pull/298) — `fix(customer): categories browse 500 from client-boundary tree helper`                                               |
| PR state                          | **MERGED** at `2026-07-19T01:32:45Z`                                                                                                                                           |
| Merge commit                      | `b17c311c857b9b610b0a8003e291c81ad2da1e15`                                                                                                                                     |
| Fix commit                        | `726b0d47aa3d6732e660e2ee43f3533465897893` (`category-tree.ts` extraction)                                                                                                     |
| `origin/master` tip at check      | `e4464f0` (includes #298, #299, #300)                                                                                                                                          |
| Vercel project                    | `convergeo-customer` (`prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`), team `vergeo-projects`                                                                                              |
| **Current production deployment** | `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW`                                                                                                                                             |
| Production commit SHA             | **`cc4a8241d25e4c715903ba4ca161fb95491ff52b`**                                                                                                                                 |
| Production git ref                | `master` — message: _Merge pull request #296…_                                                                                                                                 |
| Production readyAt                | `2026-07-19T00:17:40.271Z` (**before** #298 merge)                                                                                                                             |
| Production aliases                | `www.vergeo5.com`, `vergeo5.com`, `convergeo-customer.vercel.app`, `convergeo-customer-vergeo-projects.vercel.app`, `convergeo-customer-git-master-vergeo-projects.vercel.app` |
| Inspector                         | https://vercel.com/vergeo-projects/convergeo-customer/9uNbPuvwmuWPGZUTZMm564BaVRHW                                                                                             |

### Drift proof

| Check                                                 | Result                                                                                                 |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `cc4a824` ancestor of `b17c311`?                      | Yes                                                                                                    |
| `category-tree.ts` at production SHA `cc4a824`        | **MISSING**                                                                                            |
| `category-tree.ts` at #298 merge `b17c311`            | Present                                                                                                |
| Production page import (`cc4a824`)                    | `import { buildCategoryTree } from "../_components/category-mega-menu"` (client module)                |
| #298 page import                                      | Uses `fetchCategoriesResult` + server-safe tree helper (fix)                                           |
| Any production-target Vercel deploy after #298 merge? | **None** in the listed recent deployments (latest `target=production` remains `dpl_9uNb…` / `cc4a824`) |

---

## 2. Route probes

Method: `curl -sS -L` from this agent host, User-Agent `Vergeo5PostDeployCheck/1.0`.  
Apex `vergeo5.com` returns **308** → `www.vergeo5.com` (expected); final status is what matters for success criteria.

| Requested URL                     | First hop | Final URL                             | Final HTTP | Populated / empty / unavailable                   | Client/server-boundary error? |
| --------------------------------- | --------- | ------------------------------------- | ---------- | ------------------------------------------------- | ----------------------------- |
| https://vergeo5.com/en/categories | 308       | https://www.vergeo5.com/en/categories | **500**    | N/A — page aborted (not honest empty/unavailable) | **Yes** — digest `3012388270` |
| https://vergeo5.com/fr/categories | 308       | https://www.vergeo5.com/fr/categories | **500**    | N/A — page aborted                                | **Yes** — digest `3012388270` |
| https://vergeo5.com/zh/categories | 308       | https://www.vergeo5.com/zh/categories | **500**    | N/A — page aborted                                | **Yes** — digest `3012388270` |

### Success criteria

| Criterion                       | Required | Observed                                             |
| ------------------------------- | -------- | ---------------------------------------------------- |
| HTTP 200 every locale           | Yes      | **FAIL** — 500 / 500 / 500                           |
| No client/server-boundary error | Yes      | **FAIL** — `buildCategoryTree` client-boundary throw |

Control: `GET https://www.vergeo5.com/en/health` → **200** `{"status":"ok","app":"customer"}` (same production deployment).

### HTML / RSC surface (each locale)

- Metadata still renders (titles: EN `Browse categories \| Vergeo5`; FR `Parcourir les catégories \| Vergeo5`; ZH `浏览分类 \| Vergeo5`).
- Document root includes `id="__next_error__"`.
- RSC flight payload contains: `6:E{"digest":"3012388270"}`.
- Visible body is not a populated catalogue, not `categories-empty`, and not `categories-unavailable-*` — the Server Component body fails before those honest states can render.
- Browser console was not instrumented in a headed browser; the same digest and error text appear in Vercel runtime logs (below). No separate client-only exception beyond the Next error shell is required to diagnose this failure.

---

## 3. Vercel runtime errors (production)

Project `convergeo-customer`, environment `production`, deployment **`dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW`**, branch `master`, ~01:48–01:49Z:

```text
Error: Attempted to call buildCategoryTree() from the server but buildCategoryTree is on the client.
It's not possible to invoke a client function from the server, it can only be rendered as a Component
or passed to props of a Client Component.
digest: '3012388270'
```

Observed on `GET /en/categories`, `GET /fr/categories`, `GET /zh/categories` (status 500 / error).  
Stack points at `.next/server/app/[locale]/(shop)/categories/page.js` — matches pre-#298 code on `cc4a824`.

**Vercel runtime error digest:** `3012388270` (identical across en/fr/zh; matches prior root-cause note in `docs/production-readiness/2026-07-18/implementation/categories-500-root-cause.md`).

---

## 4. Diagnosis (deployment drift — not a new code regression)

1. PR #298 fixed the client-boundary import and is on `master` (`b17c311`).
2. Customer production aliases still serve **`dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW` @ `cc4a824`** (PR #296), created ~75 minutes before #298 merged.
3. Therefore production still executes `buildCategoryTree` from `"use client"` `category-mega-menu.tsx` → HTTP 500 / digest `3012388270`.
4. This is **not** evidence that the #298 fix failed at runtime in production; the fix commit is **not present** on the live deployment.

---

## 5. Evidence needed to clear FAIL (ops — out of scope for this check)

No code PR opened from this verification (per instructions).

To re-verify after promotion:

1. Confirm a new `convergeo-customer` deployment with `target=production` whose `meta.githubCommitSha` is **`b17c311…` or a later master SHA that contains #298** (currently tip `e4464f0` also contains it).
2. Confirm production aliases (`www.vergeo5.com` / `vergeo5.com`) point at that deployment id.
3. Re-probe en/fr/zh `/categories` → expect **HTTP 200** and one of: populated links, honest empty (`categories-empty*`), or honest unavailable (`categories-unavailable-*`) — **not** digest `3012388270`.
4. Confirm Vercel runtime logs for those paths no longer show the `buildCategoryTree` client-boundary error.

---

## 6. Probe appendix

| Field                           | Value                                             |
| ------------------------------- | ------------------------------------------------- |
| Deployed commit (customer prod) | `cc4a8241d25e4c715903ba4ca161fb95491ff52b`        |
| Deployed build / deployment id  | `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW`                |
| Expected fix commit (not live)  | `b17c311c857b9b610b0a8003e291c81ad2da1e15` (#298) |
| Error digest                    | `3012388270`                                      |
| Overall                         | **FAIL**                                          |
