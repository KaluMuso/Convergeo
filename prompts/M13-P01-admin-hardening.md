> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. Stay dep-free (M04-P07 owns Python deps). **Only this pebble touches `infra/Caddyfile` this wave.**

# M13-P01 — Admin hardening & shell

## 1. Context

**Wave 5 (parallel ×6).** Grounded against as-built `master`:

- **`apps/admin/middleware.ts` already composes admin-role gating + locale** (M04-P03): it uses `@vergeo/auth` `updateSession` + `shouldRedirectToLogin('admin', …)` + an `isAdminBypassActive()` **non-prod bypass flag**, with a `// M13-P01: Cloudflare Access header enforcement replaces this non-prod bypass.` marker. **You COMPOSE the CF-Access JWT assertion onto this — do NOT drop the locale routing or the existing gate.** In prod, require the CF-Access header/JWT; keep the bypass **non-prod only**.
- **Admin app layout is `apps/admin/app/[locale]/layout.tsx`** (exists) — you edit THAT (nav shell), not a root `app/layout.tsx` (the spec path is stale). Admin app is already `noindex` (robots).
- API: `services/api/app/` has `core/` (auth: `require_role`), `errors.py`, `main.py` (router **auto-discovery** — never edit), `supabase_client.py` (service-role). **`audit_log` table exists** (`0007_trust_ops.sql`, service-role-only). `core/auth.py`'s `require_role('admin')` reads roles from `user_roles` (never JWT).
- **`infra/Caddyfile` exists** — you add the admin vhost hardening (IP allowlist + CF Access) here. `packages/i18n/messages/en/admin.json` exists but is a **buggy flat-dotted skeleton** (`"admin.title": …`) → next-intl nests on dots, so **rewrite it nested without the redundant `admin.` prefix** (pattern: `legal.json`).
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P01.

## 2. Objective & scope

Hardened admin origin: CF-Access-asserted middleware, a nav-shell layout, and a **transparent audit middleware** so every admin-role mutation writes `audit_log` (before/after) with no opt-out.
**Non-goals:** no admin feature pages (KYC/moderation/orders queues are later M13 pebbles), no new tables (audit_log exists), no Caddy deploy (config only).

## 3. Files (create/modify ONLY these)

- **Modify:** `apps/admin/middleware.ts` (compose CF-Access assertion onto the existing admin gate — locale + bypass preserved) · `apps/admin/app/[locale]/layout.tsx` (admin nav shell) · `infra/Caddyfile` (admin vhost: IP allowlist + CF Access) · `packages/i18n/messages/en/admin.json` (nest + fill shell strings)
- **Create:** `services/api/app/core/admin_audit.py` (audit middleware/dependency: admin-role mutation → `audit_log` with before/after diff) · `services/api/app/routers/admin_base.py` (base admin router wiring the audit + `require_role('admin')`) · `services/api/tests/test_admin_audit.py` · `docs/ops/admin-access.md`
  **Guardrail: nothing else. Do NOT edit `core/auth.py`/`__init__.py`, `main.py`, other apps' middleware, `packages/i18n/src/request.ts` (`admin` is already registered), or any migration.**

## 4. Implementation spec

- **Middleware:** keep the M04-P03 composition; add: in prod (`NODE_ENV==='production'` and not bypass) **require the Cloudflare Access JWT/header** (assert presence + validity of `Cf-Access-Jwt-Assertion`; full JWKS verify may be stubbed with a documented TODO if the CF team keys aren't wired yet, but presence must be enforced). Non-admin JWT → 403/redirect **before any handler**. Bypass flag stays non-prod-only.
- **`core/admin_audit.py`:** a transparent mechanism (FastAPI dependency or middleware) that, for every **mutating** admin request (POST/PUT/PATCH/DELETE under the admin routers), captures before/after state and writes an `audit_log` row (`actor`, `action`, `entity_type`, `entity_id`, `before`, `after`) via the service-role client. **Opt-out impossible for mutations** — wire it at the `admin_base` router level so any admin router inherits it. A mutation that somehow writes without an audit row must fail a test hook.
- **`routers/admin_base.py`:** an `APIRouter` (or factory) that bundles `require_role('admin')` + the audit dependency; future M13 routers mount on it. Include a trivial health/echo admin route to exercise the audit in tests (auto-discovered).
- **Layout:** minimal hardened admin nav shell (server component), tokens only, `admin.*` i18n keys, no public assets.
- **`infra/Caddyfile`:** admin vhost with IP allowlist + CF Access comments/directives; document real values live in env/secret, not the file. `docs/ops/admin-access.md`: how prod access works (CF Access + allowlist) and the non-prod bypass.

## 5–8. UI/UX · Responsiveness · Performance · SEO

Admin shell functional/hardened; `noindex`; no SEO. Edge-light middleware.

## 9. Security

Non-admin → 403 before handlers; prod requires CF Access; audit completeness enforced (mutation without audit row fails a test); service-role confined (audit writes via the one service-role module); bypass non-prod only; roles from DB (never JWT).

## 10. Tests (RUN before reporting)

`test_admin_audit.py`: an admin mutation writes exactly one `audit_log` row with before/after; a mutation path that skips audit fails; non-admin → 403 (`uv run pytest`, `ruff`, `mypy`). Middleware unit: non-admin redirected/403, admin passes, **locale still applied**, prod-without-CF-header blocked, non-prod bypass works. i18n completeness for `admin.*` (nested, no flat keys). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. Validate `Caddyfile` syntax (`caddy validate` if available, else structural check).

## 11. Acceptance criteria / DoD

- [ ] Non-admin JWT → 403 before any handler; prod requires CF Access; bypass non-prod only.
- [ ] Every admin mutation writes `audit_log` (before/after); opt-out impossible (tested).
- [ ] Caddyfile admin vhost hardened; `admin.json` nested; locale routing preserved; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M13-P01 — Admin hardening & shell
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste audit-completeness + non-admin-403 + middleware-matrix + i18n output
**EXCERPTS:** full `admin.middleware.ts` composition + `admin_audit.py` core (authz/audit surfaces) — nothing else
**QUESTIONS:** (or "none")
