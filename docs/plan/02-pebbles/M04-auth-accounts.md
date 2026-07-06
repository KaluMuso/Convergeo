# M04 — Auth & Accounts — Pebbles

7 pebbles. Phone-OTP is the primary door; roles live in JWT claims + `user_roles` (server-managed). Every mutating endpoint from here on: authz dependency + Pydantic strict + rate limit (rule #3).

---

### M04-P01 — Supabase Auth configuration & SMS hook `M`
**Deps:** M03-P01 · **Files:** `supabase/config.toml` (auth section), `supabase/functions/sms-hook/` (edge function: Africa's Talking send-OTP), `supabase/functions/profile-bootstrap/` (on-signup trigger → `profiles` row + default customer role), `docs/ops/auth-providers.md`
Phone OTP (custom SMS hook → Africa's Talking), email+password, Google OAuth config (redirect URLs per app origin); profile bootstrap on first signup; auth email templates (branded, i18n-keyed EN).
**AC:** local stack: phone signup issues OTP via mocked AT client; profile + role row created exactly once (idempotent on retry); Google flow documented with exact console steps.
**Tests:** edge function unit tests (AT payload shape, retry-safe); bootstrap idempotency.

### M04-P02 — API auth dependency & role guards `M`
**Deps:** M03-P01, M01-P02 · **Files:** `services/api/app/core/auth.py` (JWT verify via JWKS, `CurrentUser`, `require_role(...)` dependencies), `app/core/supabase.py` (per-request user-token client; **service-role client in an isolated module with lint guard** — importable only from `app/core/`), `services/api/tests/test_auth_dep.py`
FastAPI dependencies: verified JWT → user id + roles; role claims read from `user_roles` (cached per request); tampered/expired token → 401 envelope; role-forging via client-supplied claims impossible (claims re-checked against DB for admin).
**AC:** forged admin claim in JWT payload without DB role → 403; service-role usage greppable to one module.
**Tests:** expired/tampered/none tokens; role escalation attempts; service-role import lint test.

### M04-P03 — Frontend auth clients & middleware guards `M`
**Deps:** P01, M01-P05 · **Files:** `packages/auth/` (supabase browser/server clients, `useSession`, role helpers), `apps/customer/middleware.ts` (replace stub: locale + optional-auth), `apps/vendor/middleware.ts` (require vendor role), `apps/admin/middleware.ts` (require admin role + non-prod bypass flag)
Session refresh rotation; role-gated app entry (vendor/admin bounce to login; admin additionally expects Cloudflare Access header in prod — enforced fully in M13-P01).
**AC:** unauthenticated vendor/admin access redirects; customer app browsable logged-out; session survives refresh.
**Tests:** middleware unit tests per role/route matrix.

### M04-P04 — Auth UI (login/signup/OTP) `M`
**Deps:** P03, M02-P03 · **Files:** `apps/customer/app/[locale]/(auth)/login/page.tsx`, `signup/page.tsx`, `otp/page.tsx` (+ shared form components under `(auth)/_components/`), `apps/vendor/app/(auth)/login/page.tsx`, `apps/admin/app/(auth)/login/page.tsx`, `packages/i18n/messages/en/auth.json`
Phone-first (country code +260 default), OTP entry (M02 OTPField) with resend countdown; email+password and Google as alternates; error states (wrong code, expired, throttled) all i18n-keyed.
**AC:** signup→browse on phone number only at 360px; resend disabled during cooldown; a11y labels complete.
**Tests:** component tests: happy path, wrong OTP, resend cooldown; e2e-lite via mocked auth.

### M04-P05 — Account pages `M`
**Deps:** P04, M03-P04 · **Files:** `apps/customer/app/[locale]/account/` (`page.tsx` profile, `addresses/page.tsx`, `preferences/page.tsx`), `services/api/app/routers/account.py`, `packages/i18n/messages/en/account.json`
Profile edit (name, locale); addresses CRUD: label, **landmark text + GPS pin** (geolocation capture, lightweight static-map preview, manual lat/lng adjust — no heavy map lib), phone; language preference; notification channel prefs (WhatsApp/SMS/email toggles feeding M14).
**AC:** address saves landmark+lat/lng; locale switch re-renders app; prefs persisted and RLS-scoped.
**Tests:** router tests (authz: user A cannot edit B's address), geolocation-denied fallback.

### M04-P06 — DPA export & deletion `M`
**Deps:** P05 · **Files:** `services/api/app/routers/privacy.py`, `apps/customer/app/[locale]/account/privacy/page.tsx`, `docs/ops/data-retention.md`
Zambia DPA: data export (JSON bundle of profile/addresses/orders/reviews, async job → signed download), account deletion (auth user removed; PII anonymized; orders/ledger retained anonymized for tax/audit per retention doc); confirmation friction (typed phrase + OTP).
**AC:** deletion cascades correctly (re-login impossible; orders remain anonymized; ledger untouched); export contains all user-linked tables.
**Tests:** deletion cascade assertions per table; export completeness test; deletion requires re-auth.

### M04-P07 — Rate limiting & OTP abuse guards `M`
**Deps:** P01, P02 · **Files:** `services/api/app/core/ratelimit.py` (SlowAPI + Postgres-backed counters — no Redis in stack), `app/routers/auth_guard.py`, migration `supabase/migrations/00xx_rate_counters.sql`, `services/api/tests/test_ratelimit.py`
Per-number and per-IP OTP caps (e.g. 5/hour/number, 20/day/IP), exponential resend cooldown, global auth-endpoint rate limits; lockout + i18n-keyed retry-after messaging; counters table with TTL cleanup.
**AC:** brute-force script blocked (tested); legit resend flow unaffected; limits config-table-tunable.
**Tests:** cap breach → 429 with retry-after; window expiry restores; per-number vs per-IP independence.
