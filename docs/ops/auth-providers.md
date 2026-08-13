# Auth providers — Supabase Auth setup (Vergeo5)

Phone OTP (primary), email+password, and Google OAuth. Secrets are env-only — never commit values.

## Environment variables (names only)

| Variable                                  | Used by                                                     |
| ----------------------------------------- | ----------------------------------------------------------- |
| `SUPABASE_URL`                            | API + Next.js server-side                                   |
| `SUPABASE_ANON_KEY`                       | Server-side anon key                                        |
| `NEXT_PUBLIC_SUPABASE_URL`                | Customer/vendor/admin **browser** clients (`packages/auth`) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`           | Customer/vendor/admin **browser** clients (`packages/auth`) |
| `SUPABASE_SERVICE_ROLE_KEY`               | API server-side only                                        |
| `SEND_SMS_HOOK_SECRET`                    | Supabase Auth Send SMS Hook + `send-sms-otp` edge function  |
| `AT_API_KEY`                              | `send-sms-otp` edge function                                |
| `AT_USERNAME`                             | `send-sms-otp` edge function                                |
| `AT_SENDER_ID`                            | `send-sms-otp` edge function (alphanumeric sender ID)       |
| `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID` | Supabase Auth Google provider                               |
| `SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET`    | Supabase Auth Google provider                               |

Copy names from `.env.example`; fill values in your local `.env` / secret store.

## Phone OTP — Africa's Talking + Send SMS Hook

Africa's Talking is **not** a built-in Supabase SMS provider. Vergeo5 uses Supabase's **Send SMS Hook** → edge function `send-sms-otp` → AT REST API.

### 1. Africa's Talking dashboard

1. Sign up at [africastalking.com](https://africastalking.com) and create an app (sandbox for dev).
2. Note **Username** (sandbox username is usually `sandbox`) → `AT_USERNAME`.
3. **Settings → API Key** → generate key → `AT_API_KEY`.
4. **SMS → Sender IDs** (or sandbox): register/request sender ID (e.g. `VERGEO5`) → `AT_SENDER_ID`.
5. Sandbox: add test phone numbers under **SMS → Phone numbers** before sending real OTPs.

### 2. Send SMS Hook secret

1. Supabase Dashboard → **Authentication → Hooks** → **Send SMS** → HTTPS.
2. URL (hosted): `https://<project-ref>.supabase.co/functions/v1/send-sms-otp`
3. Click **Generate secret** → copy `v1,whsec_<base64>` → `SEND_SMS_HOOK_SECRET`.
4. Deploy the edge function with `AT_*` secrets in the function environment.

**Local (`supabase start`):** `supabase/config.toml` wires:

```toml
[auth.hook.send_sms]
enabled = true
uri = "http://host.docker.internal:54321/functions/v1/send-sms-otp"
secrets = "env(SEND_SMS_HOOK_SECRET)"
```

Put the same `SEND_SMS_HOOK_SECRET` in the repo root `.env` (and `supabase/functions/.env` if you run the function standalone). Secret must be `v1,whsec_<base64>` (32–88 char base64 segment after prefix).

### 3. Enable phone auth in Supabase

Already set in `config.toml`:

- `[auth.sms] enable_signup = true`
- `[auth.sms] enable_confirmations = true`

Hosted: Authentication → Providers → Phone → enable.

## Google OAuth

**Current production posture:** the Google provider is **not enabled** in hosted
Supabase Auth. The Customer, Vendor, and Admin login UIs therefore **do not
render** a Google button unless `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true`.
Default is off. Do not turn the button on until the steps below are complete
and verified.

This document lists **names and requirements only**. Never commit client
secrets, service-role keys, or other secret values.

### 1. Google Cloud Console

1. [console.cloud.google.com](https://console.cloud.google.com) → create/select project.
2. **APIs & Services → OAuth consent screen** → External (or Internal for Workspace) → app name **Vergeo5**, support email, authorized domains `vergeo5.com` (prod).
3. **Credentials → Create credentials → OAuth client ID** → type **Web application**.
4. **Authorized JavaScript origins** (exact origins; include `www` and apex separately):

   | App             | Origin                       |
   | --------------- | ---------------------------- |
   | Customer        | `http://127.0.0.1:3000`      |
   | Vendor          | `http://127.0.0.1:3001`      |
   | Admin           | `http://127.0.0.1:3002`      |
   | Customer (prod) | `https://vergeo5.com`        |
   | Customer (www)  | `https://www.vergeo5.com`    |
   | Vendor (prod)   | `https://vendor.vergeo5.com` |
   | Admin (prod)    | `https://admin.vergeo5.com`  |

5. **Authorized redirect URIs** — Google must redirect to **Supabase Auth**, not the Next.js apps. Add **one URI per Supabase project**:

   | Environment | Redirect URI                                         |
   | ----------- | ---------------------------------------------------- |
   | Local       | `http://127.0.0.1:54321/auth/v1/callback`            |
   | Hosted      | `https://<project-ref>.supabase.co/auth/v1/callback` |

   Production project ref is documented in `infra/staging/forbidden-production-identifiers.env` as `PROD_SUPABASE_PROJECT_REF`. Staging uses a **different** project.

6. Copy **Client ID** → `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID`, **Client secret** → `SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET`.

### 2. Supabase Auth Google provider

Do **not** enable this from application code. In the hosted Dashboard:

1. Authentication → Providers → Google → enable.
2. Paste the Google OAuth **client ID** and **client secret** (names above).
3. Save. Confirm the provider shows as enabled before exposing any UI.

Local `config.toml`:

```toml
[auth.external.google]
enabled = true
client_id = "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID)"
secret = "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET)"
skip_nonce_check = true
```

`skip_nonce_check = true` is for local Google sign-in. Re-evaluate before production hardening.

### 3. Site URL and allowed redirect URLs (exact origin)

Supabase Auth redirects the browser back to the portal that started OAuth.
These must be **exact origins** (scheme + host + optional port, no path glob
unless explicitly supported by the hosted project):

**Production site URL:** `https://vergeo5.com`

**Allowed redirect URLs:**

| Portal   | Production                      | Local                      |
| -------- | ------------------------------- | -------------------------- |
| Customer | `https://vergeo5.com/**`        | `http://127.0.0.1:3000/**` |
| Customer | `https://www.vergeo5.com/**`    |                            |
| Vendor   | `https://vendor.vergeo5.com/**` | `http://127.0.0.1:3001/**` |
| Admin    | `https://admin.vergeo5.com/**`  | `http://127.0.0.1:3002/**` |

The Next.js apps complete the PKCE exchange on `/{locale}/login?code=…`.
Wildcard `*` is not a substitute for listing each portal origin.

### 4. Staging / Preview redirect strategy

- Staging Supabase project ≠ production project. Configure Google on staging
  separately (or leave it disabled).
- Vercel Preview deployments use generated `*.vercel.app` hosts. Either:
  - keep Google **disabled** on Preview (`NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` unset), or
  - add each allowed Preview origin to Supabase `additional_redirect_urls` **and**
    Google Authorized JavaScript origins. Do not reuse production redirect URLs
    for Preview.
- Preview frontends must use `https://api.staging.vergeo5.com`, never
  `https://api.vergeo5.com`.

### 5. Expose the button only after verification

Frontend flag: `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` (inlined at build).

1. Enable the Google provider in the **target** Supabase project.
2. Confirm a test OAuth round-trip from a non-production origin (or a
   throwaway Preview) returns a session, not `Unsupported provider`.
3. Set `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true` on that environment only.
4. **Rebuild** Customer, Vendor, and Admin. A runtime env change is not enough.
5. If the flag is absent, empty, or any value other than `true`, no portal
   renders an operational Google button.

Do not enable Google in production from this repository change.

## Profile bootstrap (database)

Migration `0010_profile_bootstrap.sql` adds `on_auth_user_created` on `auth.users`: inserts `profiles(id)` then `user_roles(user_id, 'customer')`, both `ON CONFLICT DO NOTHING`. No client can invoke this — only new auth signups fire the trigger.

## Email + password

Enabled via `[auth.email] enable_signup = true` in `config.toml`. Configure production SMTP in the Supabase dashboard when leaving local dev (Inbucket on `:54324` locally).

## Quick verification

```bash
# Edge function unit tests (mocked AT — no network)
deno test --allow-env supabase/functions/send-sms-otp/index.test.ts

# DB migrations through 0010 + pgTAP bootstrap test
supabase db reset
supabase test db
```
