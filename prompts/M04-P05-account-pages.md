> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** (no migrations, no `db.ts`). Stay dep-free.

# M04-P05 — Account pages

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- Auth is live: `@vergeo/auth` (SSR clients, `useSession`, roles), composed middleware, and auth UI (M04-P04) under `apps/customer/app/[locale]/(auth)/`. There is **no `account/` dir yet — you create it** at `apps/customer/app/[locale]/account/`.
- **`addresses` schema** (`0002`/`0004`): confirm exact columns before coding — read `supabase/migrations/000*.sql` for the `addresses` table (label, landmark, lat/lng, phone, `user_id` owner). RLS is owner-scoped (customer reads/writes own). **Notification prefs** live on `profiles` or a prefs column — grep the merged schema; do not invent columns.
- API: routers auto-discover via `pkgutil` (never edit `main.py`); `core/auth.py` provides `get_current_user`/`require_role`; per-request user-token client in `core/supabase.py` (RLS applies as caller). Error envelope `{"error":{code,message,details,request_id}}`.
- i18n `account` namespace is already registered with a loader; `packages/i18n/messages/en/account.json` exists as a **flat-dotted skeleton** — rewrite nested (no `account.` prefix), pattern = `legal.json`. **You solely own `account.json` this wave.**
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P05.

## 2. Objective & scope

Customer account: profile edit, addresses CRUD (landmark + GPS), locale + notification-channel preferences.
**Non-goals:** DPA export/delete (M04-P06 — you only create the `account/` shell + a `privacy` i18n section it consumes), no vendor/admin account, no new deps/schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/account/layout.tsx` (account nav shell) · `account/page.tsx` (profile) · `account/addresses/page.tsx` · `account/preferences/page.tsx` · `account/_components/*` · `services/api/app/routers/account.py` · `services/api/tests/test_account.py`
- **Modify:** `packages/i18n/messages/en/account.json` (nest + fill; **include a `privacy` section** whose keys M04-P06 will consume — coordinate: title, export/delete CTAs, confirmation copy, retention note)
  **Guardrail: nothing else. Do NOT create `account/privacy/` (M04-P06 owns it), no `main.py`, no schema/`db.ts`, no other namespace.**

## 4. Implementation spec

- **`account.py`:** authed routes (via `get_current_user` + user-token client so RLS enforces ownership): GET/PATCH profile (name, locale); addresses CRUD (label, landmark text, lat/lng doubles, phone); preferences (notification channel toggles WhatsApp/SMS/email → the real prefs column/table you grounded). Every mutation authz-checked + Pydantic-validated; user A cannot edit user B's address (RLS + explicit check).
- **Profile page:** name + locale edit; locale switch re-renders the app (next-intl).
- **Addresses:** CRUD list/create/edit; **landmark text + GPS pin** — browser geolocation capture, a lightweight static-map preview (no heavy map lib — an `<img>` static tile or inline SVG), manual lat/lng adjust; geolocation-denied fallback (manual entry).
- **Preferences:** channel toggles feeding M14; persisted + RLS-scoped.
- All copy via `account` namespace; tokens only; 360px-first; a11y labels.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first, thumb-reachable; server components + minimal client JS; account pages `noindex`; RLS-scoped writes only (anon key client / user-token API), never service-role; no secrets.

## 10. Tests (RUN before reporting)

`test_account.py`: profile GET/PATCH; address CRUD; **authz — user A cannot read/edit user B's address (403/0 rows)**; preference persistence (`uv run pytest`, `ruff`, `mypy`). Component tests: geolocation-denied fallback, locale switch. i18n completeness for `account.*` (nested, incl. `privacy` section). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Address saves landmark + lat/lng; geolocation-denied fallback works.
- [ ] Locale switch re-renders; prefs persisted + RLS-scoped; cross-user edit denied (tested).
- [ ] `account.json` nested incl. `privacy` section; no schema/db.ts/deps; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M04-P05 — Account pages
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none") — note the exact prefs column/table you grounded
**TESTS:** paste authz + build + i18n output
**EXCERPTS:** the address authz check in `account.py` — nothing else
**QUESTIONS:** (or "none")
