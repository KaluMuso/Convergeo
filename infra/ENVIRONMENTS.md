# Environments — Vergeo5

Secret **names only** — never commit values. See `infra/.env.example` for OCI runtime names.

## Matrix

| Concern        | Local                                         | Staging                                        | Production                           |
| -------------- | --------------------------------------------- | ---------------------------------------------- | ------------------------------------ |
| Customer app   | `pnpm dev --filter customer` (localhost:3000) | Vercel Preview or staging project              | Vercel Production (`vergeo5.com`)    |
| Vendor app     | localhost:3001                                | `vendor.staging.vergeo5.com` (OCI)             | `vendor.vergeo5.com` (OCI)           |
| Admin app      | localhost:3002                                | `admin.staging.vergeo5.com` (OCI, allowlist)   | `admin.vergeo5.com` (OCI, allowlist) |
| API            | localhost:8000 / compose                      | `api.staging.vergeo5.com`                      | `api.vergeo5.com`                    |
| Postgres/Auth  | Supabase local or dev project                 | Supabase staging project                       | Supabase production project          |
| n8n            | optional compose profile                      | `n8n.staging.vergeo5.com`                      | `n8n.vergeo5.com`                    |
| Budget posture | $0                                            | OCI Always Free + Supabase free + Vercel hobby | ≤ $50/mo all-in (D6)                 |

## Where secrets live

| Secret / config                                    | OCI `infra/.env` | Vercel (customer)               | GitHub Actions | Notes                                |
| -------------------------------------------------- | ---------------- | ------------------------------- | -------------- | ------------------------------------ |
| `SUPABASE_URL`                                     | ✓ (api)          | `NEXT_PUBLIC_*` mirror          | —              | Public URL                           |
| `SUPABASE_ANON_KEY`                                | ✓ (api)          | `NEXT_PUBLIC_*`                 | —              | Client-safe                          |
| `SUPABASE_SERVICE_ROLE_KEY`                        | ✓ (api only)     | ✗                               | —              | **Never** in customer/vendor bundles |
| `LENCO_API_TOKEN`                                  | ✓ (api)          | ✗                               | —              | Server-only                          |
| `OPENROUTER_API_KEY`                               | ✓ (api)          | ✗                               | —              | Server-only                          |
| `WHATSAPP_TOKEN` / `AT_API_KEY` / `RESEND_API_KEY` | ✓ (api)          | ✗                               | —              | Outbox workers                       |
| `CLOUDINARY_URL`                                   | ✓ (api)          | optional public cloud name only | —              | Prefer unsigned upload presets       |
| `N8N_*`                                            | ✓                | ✗                               | —              | n8n container only                   |
| `VERCEL_TOKEN`                                     | ✗                | —                               | ✓              | Deploy customer app (stub workflow)  |
| `OCI_*`                                            | ✗                | —                               | ✓              | VM provision/deploy (M01-P07+)       |

## Conventions

1. Root `.env.example` lists platform-wide names; `infra/.env.example` lists OCI compose runtime names.
2. Copy `infra/.env.example` → `infra/.env` on the VM — file mode `600`, owned by deploy user.
3. Rotations: update OCI `.env`, `docker compose up -d`, and Vercel env separately; never log values.
4. Service-role and payment keys exist **only** in the API container environment on OCI.
