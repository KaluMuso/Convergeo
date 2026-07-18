# Admin access — Vergeo5

The admin app (`admin.vergeo5.com`) is a **separate hardened origin** (D20). Access is layered: Cloudflare Access at the edge, Caddy IP allowlisting on OCI, Supabase admin role in middleware, and API `require_role('admin')` backed by `public.user_roles` (never JWT claims alone).

## Production path

1. **Cloudflare Access** — An Access application protects `admin.vergeo5.com`. Authenticated users receive a `Cf-Access-Jwt-Assertion` header on requests to the origin.
2. **Caddy (`infra/Caddyfile`)** — The admin vhost enforces:
   - `remote_ip` allowlist via `ADMIN_ALLOWED_IPS` (founder/office/VPN CIDRs).
   - Optional `ADMIN_REQUIRE_CF_ACCESS=true` to reject requests missing `Cf-Access-Jwt-Assertion` before they reach Next.js.
3. **Next.js middleware (`apps/admin/middleware.ts`)** — In production (when bypass is off), **cryptographically verifies** the `Cf-Access-Jwt-Assertion`: signature against the Cloudflare Access team JWKS (RS256, alg pinned), the expected application audience (`CF_ACCESS_AUD`), the issuer derived from `CF_ACCESS_TEAM_DOMAIN`, and token expiry. Absent, malformed, unsigned, wrong-key, wrong-audience, wrong-issuer, or expired assertions are rejected with **403** before any handler runs. Verification is **fail-closed**: in production, if `CF_ACCESS_TEAM_DOMAIN`/`CF_ACCESS_AUD` are unset the middleware rejects every request. Edge-runtime compatible (`jose`, Web Crypto — no Node-only crypto). This is an edge gate only; authoritative admin RBAC stays in the API against `user_roles`.
4. **Supabase session + role** — Middleware refreshes the session and requires the `admin` role (from JWT `app_metadata.roles` for edge gating). Authoritative checks for mutations happen in the API via `user_roles`.
5. **API audit** — Every mutating admin route mounted on `admin_base` writes `audit_log` (before/after) with no opt-out.

### Secrets and configuration (not in repo)

| Variable                         | Where                | Purpose                                                                                    |
| -------------------------------- | -------------------- | ------------------------------------------------------------------------------------------ |
| `ADMIN_ALLOWED_IPS`              | Caddy / deploy env   | CIDR allowlist for admin vhost                                                             |
| `ADMIN_REQUIRE_CF_ACCESS`        | Caddy / deploy env   | `true` in prod to enforce CF header at edge                                                |
| `ADMIN_UPSTREAM`                 | Caddy / deploy env   | Next.js admin standalone upstream                                                          |
| `CF_ACCESS_TEAM_DOMAIN`          | Admin app deploy env | CF team domain (`<team>.cloudflareaccess.com` or bare `<team>`); derives issuer + JWKS URL |
| `CF_ACCESS_AUD`                  | Admin app deploy env | Access application audience (AUD) tag the middleware requires                              |
| Cloudflare Access app + policies | Cloudflare dashboard | Identity gate for admin hostname                                                           |
| `NEXT_PUBLIC_ADMIN_BYPASS`       | **Non-prod only**    | See below                                                                                  |

## Non-production bypass

Local and staging may set:

```bash
NEXT_PUBLIC_ADMIN_BYPASS=true
```

Rules:

- Only active when `NODE_ENV !== 'production'` (`isAdminBypassActive()` in `@vergeo/auth`).
- Skips admin **role** redirect in middleware for faster iteration.
- Does **not** apply in production builds.
- Does **not** disable API `require_role('admin')` or audit middleware.

Use real Supabase test users with `admin` in `user_roles` for API testing.

## Operator checklist

- [ ] Cloudflare Access policy limits admin to founder/ops identities.
- [ ] `ADMIN_ALLOWED_IPS` updated when office/VPN IPs change.
- [ ] `ADMIN_REQUIRE_CF_ACCESS=true` on production Caddy.
- [ ] `CF_ACCESS_TEAM_DOMAIN` + `CF_ACCESS_AUD` set on the production admin deploy (middleware fails closed — 403s all requests — without them).
- [ ] `NEXT_PUBLIC_ADMIN_BYPASS` unset (or not `true`) in production admin deploy.
- [ ] Admin DNS proxied through Cloudflare (`infra/cloudflare-dns.md`).

## Related

- `infra/Caddyfile` — admin vhost
- `apps/admin/middleware.ts` — CF Access + role gate + locale
- `services/api/app/core/admin_audit.py` — mutation audit trail
- `services/api/app/routers/admin_base.py` — base admin router (future M13 queues mount here)
