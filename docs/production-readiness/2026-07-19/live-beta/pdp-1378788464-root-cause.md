# PDP digest `1378788464` — root cause & fix

**Role:** Convergeo P0 PDP Incident Hotfix Engineer  
**Date:** 2026-07-19  
**Scope:** Customer app only. No production deploy/rollback, no API/DB/n8n/payments/flags/env changes in this change-set.

This pack does **not** claim real-money readiness or open-launch readiness.

---

## 1. Incident identity

| Item                          | Value                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Live production deployment    | `dpl_CA2qcVXsCGnaorKCyr1onybCqszs` @ `28f565cbf55b78cbd7fd1074de9e50615b8a18d1`                                             |
| Symptom routes                | `/en/p/tecno-spark-20`, `/en/p/itel-a70` (and other real PDPs)                                                              |
| Digest                        | **`1378788464`**                                                                                                            |
| Runtime error                 | `Functions cannot be passed directly to Client Components…` with `{ empty, previous, next, indicator: function indicator }` |
| Categories / search on prod   | Still HTTP 200; former digests `3012388270` / `3273208722` not reproducing                                                  |
| Candidate tip before this fix | `a99777a` (and later master) — **not** Production-deployed; still contained the buggy pattern                               |

Vercel runtime log sample (production, `dpl_CA2qcVXs…`):

```text
GET /en/p/tecno-spark-20 200 [error/serverless]
Error: Functions cannot be passed directly to Client Components …
  {empty: ..., previous: ..., next: ..., indicator: function indicator}
digest: '1378788464'
```

---

## 2. Trace (server → gallery → indicator)

```text
apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx   ← Server Component
  └─ <PdpInteractiveBody galleryLabels={{ … indicator: (c,t) => t(…) }} />
        └─ apps/.../_components/pdp/comparison.tsx      ← "use client"
              └─ <PdpGallery indicatorLabel={galleryLabels.indicator} />
                    └─ packages/ui ImageGallery         ← "use client"
```

**Root cause:** the Server Component constructed a **function** for `galleryLabels.indicator` and passed it into the Client Component tree. RSC serialization rejects function props → digest `1378788464` → branded error UI (“Something went wrong”), even when HTTP status is often 200.

Not caused by:

- missing i18n messages (keys exist in en/fr/zh `catalog.json`);
- Cloudinary / empty media (empty gallery already had a labelled fallback);
- mock listing data;
- categories/search client-boundary digests (separate, already fixed).

**Prior PDP repair (#305 / `b09263e`)** introduced/kept the `indicator: (current, total) => t(...)` server→client pass. It improved gallery labels in tests but **did not** prove the live runtime digest was gone — and production still logs `1378788464`.

---

## 3. Fix (smallest customer-only patch)

| Change                                                                                                    | Purpose                                                                                               |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `page.tsx` — pass only serializable `empty` / `previous` / `next` strings                                 | Stop crossing the RSC boundary with a function                                                        |
| `comparison.tsx` (`PdpInteractiveBody`) — format indicator with client `useTranslations("catalog")`       | Keep interactive indicator text inside the client module                                              |
| `gallery-labels.ts` — `PdpGalleryLabelStrings`, `formatPdpGalleryIndicator`, `assertRscSafeGalleryLabels` | Server-safe types + regression guard for digest `1378788464`                                          |
| Tests — `gallery-labels.test.ts`, `pdp-interactive-gallery.test.tsx`                                      | Would fail on the old function-prop shape; cover en/fr/zh, multi-image, empty gallery, escrow honesty |

No PDP redesign, no mock catalogue data, no hiding failures as empty states.

---

## 4. Verification performed (this session)

### Quality gates (customer)

| Gate                               | Result                                                         |
| ---------------------------------- | -------------------------------------------------------------- |
| `pnpm --filter customer lint`      | PASS                                                           |
| `pnpm --filter customer typecheck` | PASS                                                           |
| `pnpm --filter customer test`      | PASS — 63 files / **340** tests                                |
| `pnpm --filter customer build`     | PASS (with `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`) |

### Local `next start` smoke (port 3010, live read-only API)

Env for middleware only (dummy public stubs — not production secrets):  
`NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co`, `NEXT_PUBLIC_SUPABASE_ANON_KEY=dev`,  
`NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`, `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=convergeo`.

| Route                          | HTTP                  | Digest `1378788464` | Notes                                                                                               |
| ------------------------------ | --------------------- | ------------------- | --------------------------------------------------------------------------------------------------- |
| `/en\|fr\|zh/p/tecno-spark-20` | **200**               | **absent**          | Gallery + indicator (`Image 1 of 1` / FR / ZH)                                                      |
| `/en\|fr\|zh/p/itel-a70`       | **200**               | **absent**          | Gallery + indicator                                                                                 |
| Empty / multi-image            | Covered in unit tests | —                   | Live API sample had only 1 image per product                                                        |
| `/en/categories`               | **200**               | no former digests   | Honest “Categories unavailable” when upstream fetch failed locally (`status:0`) — not the old crash |
| `/en/search?q=phone`           | **200**               | no former digests   | Result tabs populated (All 11 / Products 5)                                                         |

Buyer-trust / escrow copy still present on local PDP HTML.

**Not done:** production deploy, production Instant Rollback, payment/flag/env mutations.

---

## 5. Rollback target safety

| Target                                                 | SHA               | Independently proven safe for digest `1378788464`? |
| ------------------------------------------------------ | ----------------- | -------------------------------------------------- |
| Previous production `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` | `8928d6e…` (#312) | **No — remains unverified / likely still broken**  |

Source check: commit `b09263e` (server-passed `indicator` function) **is an ancestor** of `8928d6e`, and that SHA still contains:

```ts
indicator: (current, total) => t("pdp.gallery.indicator", { current, total }),
```

Rolling back to `dpl_7FsK2sJa…` is **not** a proven PDP fix. Prefer deploying this hotfix (Production env) after rate-limit/credentials allow.

---

## 6. Deployment & verification checklist (founder / release manager)

Do **not** promote Preview deployments. Deploy **customer** only from this PR’s merge commit (or master tip containing it) with **Production** env.

### Pre-deploy

- [ ] Confirm PR merged to `master` and Vercel rate limit cleared (or `VERCEL_TOKEN` Production deploy available)
- [ ] Record current production deployment ID/SHA for rollback (`dpl_CA2qcVXs…` @ `28f565c` as of writing — refresh at deploy time)
- [ ] Confirm no payment / `public_launch` / migration changes in the deploy

### Deploy

- [ ] Production deploy **convergeo-customer** only from the fix SHA
- [ ] Record new deployment ID, URL, SHA
- [ ] Keep previous READY production deployment available

### Post-deploy probes (must all pass)

- [ ] `GET /en/health` → `buildId` equals deployed SHA
- [ ] `/en|/fr|/zh/p/tecno-spark-20` → HTTP 200, **no** digest `1378788464`, gallery/indicator visible (or labelled empty), no “Something went wrong”
- [ ] `/en|/fr|/zh/p/itel-a70` → same
- [ ] Browser: open one PDP — console/runtime free of `Functions cannot be passed directly…`
- [ ] `/en|/fr|/zh/categories` → 200, no digest `3012388270`
- [ ] `/en|/fr|/zh/search?q=phone` → 200, no digest `3273208722`
- [ ] Escrow / buyer-trust copy still honest (no fake payment-success)

### Rollback rule

If a customer-critical PDP still shows digest `1378788464` or conversion is unusable after deploy, Instant Rollback to the **recorded pre-deploy** production deployment — knowing that `8928d6e` alone is **not** proven clear of this digest; a bad deploy of an incomplete fix should roll back to the immediate previous Production build, then re-attempt a corrected Production build.

---

## 7. Residual risks

1. Vercel free-tier deploy rate limit may still block Production builds.
2. Local smoke categories upstream `status:0` is an environment fetch flake, not this digest; re-check categories on real Production after deploy.
3. Demo catalogue may lack multi-image SKUs — empty/multi covered by unit tests; spot-check when richer media exists.
