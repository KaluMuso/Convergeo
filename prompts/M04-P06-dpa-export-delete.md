> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M04-P06 — DPA export & deletion

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- **Interface edge with M04-P05 (same wave):** M04-P05 creates the `account/` shell (`account/layout.tsx`) + owns `account.json` including a **`privacy` i18n section** for your page. You create ONLY `account/privacy/page.tsx` under that shell and **consume `account.privacy.*` keys (do NOT edit `account.json`)**. If a key is missing, list it in QUESTIONS rather than editing the file.
- API: routers auto-discover (never edit `main.py`); `core/auth.py` (`get_current_user`), user-token client in `core/supabase.py`, service-role client in `app/supabase_client.py` (the ONE service-role module — import only from there). Private artefacts go to Supabase Storage private bucket (signed URLs) — the media-signing seam exists (M05-P10).
- **User-linked tables** to export/anonymize (grep the merged schema for exact names): `profiles`, `addresses`, `orders`/`order_items`, `reviews`, `disputes`, `returns`, payments/invoices (customer-scoped). **Ledger + orders are RETAINED (anonymized) for tax/audit — never hard-deleted.** `auth.users` deletion removes login.
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P06.

## 2. Objective & scope

Zambia-DPA data export (JSON bundle → signed download) + account deletion (auth user removed, PII anonymized, orders/ledger retained anonymized), with confirmation friction.
**Non-goals:** no account shell/nav (M04-P05), no new schema (use existing tables + soft-anonymize), no new deps.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/privacy.py` · `apps/customer/app/[locale]/account/privacy/page.tsx` · `docs/ops/data-retention.md` · `services/api/tests/test_privacy.py`
  **Guardrail: nothing else. Do NOT edit `account.json`/`account/layout.tsx` (M04-P05), no `main.py`, no schema/`db.ts`, no migration.**

## 4. Implementation spec

- **Export:** `POST /account/export` → assembles a JSON bundle of all user-linked rows (profile, addresses, orders, reviews, …) read via the **user-token client** (RLS proves scope) or service-role with an explicit `user_id` filter; async job pattern → a **short-lived signed download URL** (private bucket). Must contain every user-linked table (completeness test).
- **Deletion:** `POST /account/delete` with **confirmation friction — typed phrase + fresh OTP/re-auth**. On confirm: anonymize PII in retained tables (orders/ledger/invoices → strip name/phone/address, keep amounts + ids for tax/audit), delete addresses/prefs, then remove the `auth.users` row (re-login impossible). **Ledger rows untouched.** Cascade must be correct + idempotent. Use the service-role client (confined to `app/supabase_client.py`).
- **`docs/ops/data-retention.md`:** what is deleted vs anonymized-and-retained and why (ZRA/audit), retention windows.
- Page: explains export + deletion, the friction flow, links from account (uses `account.privacy.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; `noindex`. **Security is the crux:** deletion requires re-auth (typed phrase + OTP); export/delete only ever touch the caller's own data (authz tested); signed URLs short-lived; service-role usage confined + greppable; no secrets.

## 10. Tests (RUN before reporting)

`test_privacy.py`: **export completeness** (every user-linked table present); **deletion cascade per table** (addresses gone, orders/ledger retained + anonymized, re-login impossible); **deletion requires re-auth** (missing/invalid OTP → 401/403); user cannot export/delete another user's data (`uv run pytest`, `ruff`, `mypy`). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`.

## 11. Acceptance criteria / DoD

- [ ] Export bundle covers all user-linked tables; delivered via short-lived signed URL.
- [ ] Deletion: PII anonymized, orders/ledger retained, `auth.users` removed (re-login impossible), ledger untouched.
- [ ] Deletion needs typed-phrase + OTP; cross-user denied; retention doc written; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M04-P06 — DPA export & deletion
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste export-completeness + deletion-cascade + re-auth output
**EXCERPTS:** the deletion cascade/anonymize routine in `privacy.py` — nothing else
**QUESTIONS:** (or "none") — list any `account.privacy.*` keys you need from M04-P05
