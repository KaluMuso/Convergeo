# Categories HTTP 500 — root cause and fix

**Date:** 2026-07-18 (investigation continued 2026-07-19 UTC)  
**Surface:** Customer app `GET /{locale}/categories`  
**Production tip probed:** `www.vergeo5.com` (deployment `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW`, branch `master`)  
**Scope of this change:** code fix + tests + structured logging. No production data, env, or deployment changes.

---

## 1. Reproduction (read-only)

| Probe                                           | Result                      |
| ----------------------------------------------- | --------------------------- |
| `curl -L https://vergeo5.com/en/categories`     | **HTTP 500** (apex → `www`) |
| `curl -L https://www.vergeo5.com/en/categories` | **HTTP 500**                |
| `curl -L https://www.vergeo5.com/fr/categories` | **HTTP 500**                |
| `curl -L https://www.vergeo5.com/en`            | **HTTP 200**                |

HTML for the failing route still rendered metadata successfully (`title`: “Browse categories \| Vergeo5”) and the shop chrome (nav / mega-menu shell). The RSC payload aborted the page body with:

```text
6:E{"digest":"3012388270"}
```

So the failure was **inside the categories Server Component body**, not middleware, not metadata, and not the shared shop layout alone.

---

## 2. Vercel runtime evidence

Project: `convergeo-customer` (`prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`), team `vergeo-projects`.

Runtime logs for `GET /en/categories` and `GET /fr/categories` (production, cache MISS) repeatedly showed:

```text
Error: Attempted to call buildCategoryTree() from the server but buildCategoryTree is on the client.
It's not possible to invoke a client function from the server, it can only be rendered as a Component
or passed to props of a Client Component.
digest: '3012388270'
```

Digest matches the HTML probe exactly.

---

## 3. Trace (route → render)

```text
apps/customer/app/[locale]/(shop)/categories/page.tsx   (Server Component)
  → getCatalogTranslator()          ✅ (metadata proves this works)
  → fetchCategories()               (Supabase anon via createServerClient)
  → buildCategoryTree(...)          ❌ imported from category-mega-menu.tsx
  → EmptyState / category links
```

`category-mega-menu.tsx` is marked `"use client"` because the mega-menu is an interactive disclosure. `buildCategoryTree` lived in that same module. Next.js therefore treated the function as a **client module export**. Calling it from the Server Component throws at runtime — producing the 500 — even though the function itself is pure and has no browser APIs.

### Ruled out (with evidence)

| Hypothesis                 | Evidence against                                                                                                |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Missing Supabase / API env | Home (`/en`) 200; metadata on categories works; Vercel error is the client-boundary throw, not missing-env      |
| DB empty catalogue         | Would yield empty tree / EmptyState, not digest 3012388270                                                      |
| RLS denial                 | Policy `categories_public_select` is `using (true)`; error text is not a PostgREST/RLS failure                  |
| Locale / missing i18n keys | Metadata title/description rendered for `en` and `fr`                                                           |
| Serialization / revalidate | Failure occurs before successful page serialization; digest is the client-call error                            |
| Production-only data shape | Same code path would fail with any successful query (or empty list) because the throw is pre-render of the tree |

---

## 4. Root cause (evidence-backed)

**Primary:** Server Component `CategoriesPage` imported and invoked `buildCategoryTree` from a `"use client"` module (`category-mega-menu.tsx`). Next.js App Router forbids calling client-module functions on the server → HTTP 500, digest `3012388270`.

**Secondary (correctness, not the 500):** `fetchCategories()` collapsed Supabase/config failures into `[]`, so an operational failure would have been indistinguishable from a valid empty catalogue once the client-boundary bug was fixed. Empty-state copy also labelled emptiness as “unavailable”.

---

## 5. Fix

1. Extract pure tree helpers to `apps/customer/app/[locale]/(shop)/_components/category-tree.ts` (**no** `"use client"`).
2. Import `buildCategoryTree` from that shared module in the categories Server Component; mega-menu re-exports for existing client callers/tests.
3. Introduce `fetchCategoriesResult()` with explicit `ok` / failure reasons (`config` | `unauthorized` | `upstream` | `malformed`).
4. Page maps results via `resolveCategoriesBrowseView()`:
   - populated → category links
   - empty success → honest empty EmptyState (`browseCategories.empty*`)
   - failure → unavailable EmptyState (`browseCategories.unavailable*`) with `data-testid` including reason
5. Structured `console.error` JSON log: `event=customer.categories.load_failed` with `reason` / optional `code` / `status` only — no secrets, tokens, cookies, or row payloads.
6. i18n (`en` / `fr` / `zh`): split empty vs unavailable copy.
7. Tests: populated, empty, malformed, unauthorized, upstream, config, logging shape, locale copy distinction; orphan/cycle tree behaviour.

No localhost fallback. No mock/hard-coded category catalogue in the route.

---

## 6. Verification plan (this PR)

- Customer `lint`, `typecheck`, `test`, production `build`.
- Local or preview: `GET /en/categories` and at least one other locale (`/fr/categories`) return **200** (empty or populated, never the client-boundary 500).
- Do **not** deploy from this agent run.

---

## 7. Residual risk

- Home / mega-menu still degrade query failures to an empty list (pre-existing UX). Only the dedicated browse route distinguishes empty vs unavailable.
- A truly empty production catalogue will now show the honest empty state (200), not “unavailable”.
