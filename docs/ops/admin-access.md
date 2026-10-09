# Admin access — Vergeo5

The admin app (`admin.vergeo5.com`) is a **separate hardened origin** (D20). Access is layered: Cloudflare Access at the edge, Caddy IP allowlisting on OCI, a verified JWT role hint in middleware, and API checks backed by `public.user_roles` (never JWT claims alone).

## Production path

1. **Cloudflare Access** — An Access application protects `admin.vergeo5.com`. Authenticated users receive a `Cf-Access-Jwt-Assertion` header on requests to the origin.
2. **Caddy (`infra/Caddyfile`)** — The admin vhost enforces:
   - `remote_ip` allowlist via `ADMIN_ALLOWED_IPS` (founder/office/VPN CIDRs).
   - Optional `ADMIN_REQUIRE_CF_ACCESS=true` to reject requests missing `Cf-Access-Jwt-Assertion` before they reach Next.js.
3. **Next.js middleware (`apps/admin/middleware.ts`)** — In production (when bypass is off), **cryptographically verifies** the `Cf-Access-Jwt-Assertion`: signature against the Cloudflare Access team JWKS (RS256, alg pinned), the expected application audience (`CF_ACCESS_AUD`), the issuer derived from `CF_ACCESS_TEAM_DOMAIN`, and token expiry. Absent, malformed, unsigned, wrong-key, wrong-audience, wrong-issuer, or expired assertions are rejected with **403** before any handler runs. Verification is **fail-closed**: in production, if `CF_ACCESS_TEAM_DOMAIN`/`CF_ACCESS_AUD` are unset the middleware rejects every request. Edge-runtime compatible (`jose`, Web Crypto — no Node-only crypto). This is an edge gate only; authoritative admin RBAC stays in the API against `user_roles`.
4. **Supabase session + role** — Middleware refreshes the session and accepts `admin`, `superadmin`, `moderator`, or a syntactically valid `rbac_` role from verified JWT `app_metadata.roles` for edge routing. The API reloads `user_roles` and current restricted-role grants on each request.
5. **API audit** — Every mutating admin route mounted on `admin_base` writes `audit_log` (before/after) with no opt-out.

## Configurable roles (source only until approved activation)

`superadmin` has the full admin plane and is the only role that can create, edit, delete, assign, or revoke admin roles. `admin` remains broad legacy access for compatibility but cannot manage roles; a superadmin can revoke existing legacy `admin` grants but cannot create new ones through this API. `moderator` retains product/vendor moderation. Custom roles have keys beginning `rbac_`; assignments live in the existing `public.user_roles`, and their named permission sets live in `public.admin_roles`. The API uses an explicit route/method allowlist and denies unlisted admin work.

| Grant             | Current access                                                                                                   |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| `finance.read`    | Order and dispute records, read only; no dispatch, escrow, COD collection, refund, payout, or transfer authority |
| `events.manage`   | Existing high-value event review and verification                                                                |
| `products.manage` | Existing canonical product and duplicate moderation                                                              |
| `services.read`   | Read-only service oversight                                                                                      |
| `vendors.manage`  | Vendor KYC, business, licence, and intake decisions                                                              |
| `ads.manage`      | Merchandising and promotional slots                                                                              |
| `analytics.read`  | Dashboards, search insights, clip analytics, and vendor governance reports; no kill-switch reset                 |
| `inventory.read`  | Read-only tracked-stock overview                                                                                 |

The migration adds no account grants. The `manage_admin_role` RPC rechecks the actor's live `user_roles.superadmin` row and changes roles and audit history in one transaction. Database triggers reject unknown custom keys, removal of the last superadmin, and deletion of an assigned role. Only the server's service role can invoke the RPC; browsers have no direct table or RPC grant. The Roles page accepts an existing account UUID and does not create identities. A new assignment may require the user to refresh their token before the edge middleware sees the new role, while API authorization reads the current database state.

Activation needs a separate approval for the exact shared database migration and target, source integration and deployment, the identity and grant of the first superadmin, and any changes to Cloudflare Access or other persistent credentials. Verify the registered access-token role hook and admin edge policy at the target before granting a restricted operator. No payment rail or money action is activated by these grants.

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
- Does **not** disable API role/scope checks or audit middleware.

Use isolated Supabase test users with explicit `user_roles` rows for API testing.

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
