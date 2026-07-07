> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 3 runs 5 pebbles in parallel — **touch ONLY your files below**. You are the SOLE owner of `supabase/config.toml` this wave (M03-P04 explicitly must not touch it). Do NOT touch `packages/types/src/db.ts` (M03-P04 owns it this wave).

# M04-P01 — Supabase Auth configuration & SMS hook

## 1. Context

**Wave 3 (parallel ×5).** Grounded against as-built `master`:

- `supabase/config.toml` (PG **15**) **already has a full `[auth]` section** (site_url `http://127.0.0.1:3000`, `[auth.email]` with `otp_length=6`, `[auth.sms]` with `enable_signup=false` + commented Twilio, `[auth.external.apple]` present as the template, `[auth.hook.*]` examples commented, `[edge_runtime] enabled=true deno_version=2`). **MODIFY it surgically — never regenerate/clobber.**
- `0002_identity_vendors.sql`: `profiles(id uuid PK references auth.users(id) on delete cascade, locale text not null default 'en', notif_prefs jsonb not null default '{}', …)`; `user_roles(id, user_id uuid not null references public.profiles(id), role text check in ('customer','vendor','admin'))`; helper `public.has_role(text)`. So a bootstrap must insert **profiles first, then user_roles** (FK order); only `id` is strictly required on profiles.
- **No `supabase/functions/` dir exists yet.** Africa's Talking is NOT a built-in Supabase SMS provider (built-ins: twilio/messagebird/textlocal/vonage) → use the **Send SMS Hook** (`[auth.hook.send_sms]`) pointing at an edge function.
- Env var names already declared (`.env.example` + `packages/config/src/env.ts`): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, **`AT_API_KEY`**. Reuse them; AT also needs `AT_USERNAME` + `AT_SENDER_ID` (add to `.env.example` only — see files).
- App origins: customer `:3000`, vendor `:3001`, admin `:3002`.
- Highest migration = `0008`; `0005/0006/0007/0009` are reserved (orders/money/trust/search). **Your bootstrap migration = `0010_profile_bootstrap.sql`.**
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P01.

## 2. Objective & scope

Configure phone-OTP (Africa's Talking via Send SMS Hook), email+password, Google OAuth; on-signup profile+role bootstrap; document provider setup.
**Non-goals:** no app UI / middleware (M04-P04/P05), no API auth dependency (M04-P02), no OTP rate-limit tables (M04-P07), no `db.ts` edits (M03-P04 owns it — your migration adds only a function+trigger and must not change the generated `public` types; if `gen-types` would change db.ts, STOP and note it).

## 3. Files (create/modify ONLY these)

- **Modify:** `supabase/config.toml` (auth section only), `.env.example` (append `AT_USERNAME=`, `AT_SENDER_ID=`, `SEND_SMS_HOOK_SECRET=` — names only), `packages/config/src/env.ts` (add those three to the schema, mirroring the existing `AT_API_KEY` entry)
- **Create:** `supabase/migrations/0010_profile_bootstrap.sql` + `supabase/tests/0010_profile_bootstrap.test.sql` · `supabase/functions/send-sms-otp/index.ts` (+ `deno.json` if needed) · `supabase/functions/send-sms-otp/index.test.ts` · `docs/ops/auth-providers.md`
  **Guardrail: nothing else. Do NOT touch db.ts, 0005, or any app.**

## 4. Implementation spec

- **config.toml `[auth]` edits:** `additional_redirect_urls` = the three app origins (http://127.0.0.1:3000/3001/3002 + `https://vergeo5.com` placeholder comment); `[auth.sms] enable_signup = true`, `enable_confirmations = true`; add `[auth.hook.send_sms] enabled = true` + `uri = "http://host.docker.internal:54321/functions/v1/send-sms-otp"` (documented) + `secret = "env(SEND_SMS_HOOK_SECRET)"`; enable `[auth.external.google] enabled = true`, `client_id = "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID)"`, `secret = "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET)"`, `skip_nonce_check = true` (local Google). Keep every other line intact.
- **Send SMS Hook edge function (`send-sms-otp/index.ts`, Deno):** verify the hook payload signature/secret against `SEND_SMS_HOOK_SECRET` (Supabase signs with a base64 `v1,whsec_…` secret — implement the standard verification), extract `{ user: { phone }, sms: { otp } }`, POST to Africa's Talking (`https://api.africastalking.com/version1/messaging`, headers `apiKey: AT_API_KEY`, `username`, form body `to`/`message`/`from=AT_SENDER_ID`), map AT errors to retryable/permanent, return 200 on success. **AT client behind a thin function so the test injects a mock** (no real network in tests).
- **`0010_profile_bootstrap.sql`:** `create function public.handle_new_user() returns trigger security definer set search_path = public …` inserting `profiles(id)` then `user_roles(user_id, role) values (new.id, 'customer')`, both **idempotent (`on conflict do nothing`)**; `create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();`. Comment why security-definer + search_path pinned.
- **`docs/ops/auth-providers.md`:** exact Google Cloud console steps (authorized redirect URIs per app origin + Supabase callback), AT dashboard steps (username, sender id, sandbox), Send SMS Hook wiring, and the full env-var-name list (never values).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A.

## 9. Security

Hook secret verified before trusting payload; AT creds + Google secret from env only (never committed); service-role/definer function pinned search_path; profile bootstrap can't be triggered by clients (fires on `auth.users` insert only).

## 10. Tests (RUN before reporting)

- Edge function unit test: valid signed payload → AT client called with correct `to`/`message`/`from`; bad signature → rejected; AT 4xx → permanent, 5xx → retryable (mock AT). Run via `deno test` (document the command).
- `0010` migration test (pattern per `supabase/tests/0002_*`): applying it then simulating an `auth.users` insert creates exactly one profiles row + one `user_roles('customer')` row; **re-running the insert path is idempotent** (no duplicate role). If pure-SQL simulation of an auth.users insert is constrained locally, insert directly into `auth.users` in the test transaction and assert the trigger effect.
- `supabase db reset` applies `0001→0010` clean (paste tail).
- Confirm `pnpm --filter @vergeo/config typecheck` passes with the 3 new env vars; `git diff --exit-code packages/types/src/db.ts` shows **no change** (prove the migration didn't alter generated types).

## 11. Acceptance criteria / DoD

- [ ] config.toml auth edits surgical (diff shows only added/changed auth keys); Google + phone-OTP + Send SMS Hook configured.
- [ ] Edge function sends via AT with signature verification (tested, mocked); errors classified.
- [ ] Profile+customer-role bootstrap idempotent (tested); `db reset` clean through 0010.
- [ ] `db.ts` untouched + unchanged by gen-types; env schema extended; no app files touched.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M04-P01 — Supabase Auth configuration & SMS hook
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste db reset + bootstrap-idempotency + edge-function output
**EXCERPTS:** full code of the send-sms-otp signature-verification + AT-send path, and the `handle_new_user()` function (security surfaces) — nothing else
**QUESTIONS:** (or "none")
