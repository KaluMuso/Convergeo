> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **Run `pnpm --filter customer build/typecheck/lint/test` before reporting.**

# M06-P04 — Ask Vergeo UI

## 1. Context

**Grounded against as-built `master` (M06-P02 `/ask` + M06-P03 quota MERGED):**

- **`POST /ask` is NON-STREAMING** (M06-P02, merged). It returns the full answer at once — `AskResponse` (`services/api/app/routers/ask.py`): `{ answer: string, citations: CitationRef[], cached: boolean, refused: boolean, message_key: string | null }`. **Do NOT build a token-stream UI** — render the complete answer after the request resolves (spinner while pending). `CitationRef` carries the cited entity (`entity_kind` = `listing`/`event`, `entity_id`) — map each to a `ProductCard`/`EventCard`.
- **Quota states (M06-P03):** the API returns quota-exhaustion/kill-switch as `AppError` envelopes with `message_key` (e.g. `ai.quota.guestExceeded`, `ai.quota.monthlyExceeded`, `ai.quota.killSwitch`, `ai.quota.rateLimited`) — already keyed in `packages/i18n/messages/en/ai.json`. Refusal answers come back `refused: true` + `message_key = ai.answer.not_found`.
- **Bottom nav already has an "ask" slot** (`apps/customer/app/[locale]/(shop)/layout.tsx`, key `"ask"`, currently `href: /${locale}/search?q=ask`) — **repoint it to `/${locale}/ask`** (this pebble owns that one-line change; no other Wave-16 pebble touches `(shop)/layout.tsx`).
- **Zero-results teaser** lives in `(shop)/_components/search/zero-results.tsx` (owned by M05-P06, merged) — **add an "Ask Vergeo" entry** linking to `/ask?q=<the failed query>`.
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P04. **i18n `ai` (append-rule):** append `ai.ask.*` UI keys (thread, input, disclaimer already partially present — do not duplicate existing keys).

## 2. Objective & scope

Dedicated Ask Vergeo page: query input → `POST /ask` → render the answer text + cited `ProductCard`/`EventCard` rows; guest-quota countdown + signup CTA; monthly-cap / kill-switch / rate-limit messages from `message_key`; entry from the bottom-nav ask tab and from search zero-results.
**Non-goals:** no token streaming (endpoint is non-streaming), no quota/endpoint change (M06-P02/P03 — reuse), no new AI backend.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/ask/page.tsx` · `apps/customer/app/[locale]/(shop)/_components/ask/*` (client thread view, query input, answer bubble with citation cards, quota banner, signup prompt)
- **Modify:** `apps/customer/app/[locale]/(shop)/layout.tsx` (repoint the existing `ask` nav slot href to `/${locale}/ask`) · `apps/customer/app/[locale]/(shop)/_components/search/zero-results.tsx` (add the Ask Vergeo entry, deep-linking the failed query) · `packages/i18n/messages/en/ai.json` (append `ai.ask.*` — APPEND-RULE)
  **Guardrail: nothing else. Do NOT touch `ask.py`/`quota.py` (reuse), `bottom-nav` in `packages/ui` (repoint via the layout's slot data, not the component), `ProductCard`/`EventCard` (reuse as-is), other i18n namespaces.**

## 4. Implementation spec

- **`ask/page.tsx`** (works logged-out): reads `?q=` seed, renders the client thread component. Provide the `ai` namespace via a local `NextIntlClientProvider` (mirror `services/post-job/page.tsx`) since the client component uses `useTranslations("ai.*")`.
- **Thread component** (client): input → `createApiClient` `POST /ask` `{ query }` (auth token optional — guest allowed). On success render `answer` + a row of citation cards (`entity_kind==='listing'`→ProductCard linking `/p/{slug}`, `'event'`→EventCard linking `/e/{slug}`; resolve slug from the citation payload or a follow-up fetch if the citation carries only id — check `CitationRef` shape and use what it provides). On `AppError`, map `error.details.message_key || error.message_key` → the `ai.quota.*` banner; on `refused:true` show the `ai.answer.not_found` message with NO fabricated cards. Guest quota countdown + signup CTA when `ai.quota.guestExceeded`.
- **Disclaimer:** show `ai.disclaimer` under answers.

## 5–9. Security / SEO / perf

Guest-allowed (no auth required); never render raw model text as a card when `citations` is empty and `refused` (show the refusal copy); the ask route is `noindex` (dynamic, user-specific) — set `robots: { index:false }`; 360px thread; keep the route lean (no chart/markdown-heavy libs — plain text + cards); no secrets in bundle.

## 10. Tests (RUN before reporting)

Component/logic tests: quota-state rendering for each `message_key`; fetch-error (network) handling mid-request; citation → card mapping (listing vs event); empty/refused answer shows copy with no cards; zero-results entry deep-links the query. `pnpm --filter customer build`, `pnpm --filter customer typecheck`, `pnpm --filter customer lint`, `pnpm --filter customer test`.

## 11. Acceptance criteria / DoD

- [ ] Works logged-out (guest quota path); citation cards deep-link to PDP/event; 360px thread usable; no raw model text without citation cards when results existed; quota/kill-switch/rate-limit messages render from `message_key`.
- [ ] Nav ask tab + zero-results both reach `/ask`; `ai.ask.*` appended (append-rule); customer build/typecheck/lint/test green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P04 — Ask Vergeo UI
**STATUS/FILES/DEVIATIONS** (how citations map to cards; how `message_key` drives quota banners; non-streaming render) **/TESTS** (paste quota-state + fetch-error + citation-mapping + build/typecheck/lint/test tails) **/EXCERPTS** the `POST /ask` call + `message_key`→banner mapping — nothing else **/QUESTIONS**
