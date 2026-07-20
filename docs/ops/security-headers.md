# Security headers & CSP (M15-P03)

Per-origin HTTP security headers and Content-Security-Policy for Vergeo5. Target:
**Mozilla Observatory A** on every origin (staging), zero console CSP violations on
the critical E2E flows.

Owner of the header config:

- `apps/customer/next.config.ts` — customer app (Vercel).
- `apps/vendor/next.config.ts` — vendor app (Next standalone behind Caddy on OCI).
- `apps/admin/next.config.ts` — admin app (Next standalone behind Caddy on OCI, hardened origin).
- `infra/Caddyfile` — edge headers for the API, vendor, admin and n8n origins.

The customer app is served by Vercel (headers from `next.config.ts`). The vendor and
admin apps run a Next.js standalone server behind Caddy: the **app** owns CSP +
Permissions-Policy (they vary per route), and **Caddy** only sets constant baseline
headers so it does not clobber the richer per-route app values.

---

## 1. Nonce-based CSP + report-only → enforce rollout

CSP is **nonce-based**: `script-src` uses `'strict-dynamic'` + a per-request
`'nonce-…'` and **never** `'unsafe-inline'` for scripts. (`style-src` keeps
`'unsafe-inline'` — Next/Tailwind inject inline styles and CSP only forbids inline
_scripts_ here.)

Next.js injects the nonce into its own bootstrap scripts only when the nonce arrives
on the **request** (set by middleware). CCP-07a wires that middleware in all three
apps and substitutes `{{CSP_NONCE}}` in the report-only policy per request. We still
ship in two layers so nothing breaks while violations are observed:

1. **Enforced now** (`Content-Security-Policy`): the framing/hardening directives that
   do **not** govern Next's inline scripts and therefore need no live nonce —
   `base-uri`, `object-src 'none'`, `frame-ancestors`, `form-action`,
   `upgrade-insecure-requests`. These give real protection (clickjacking, base-tag
   injection, object embeds, form hijack) immediately.
2. **Report-only** (`Content-Security-Policy-Report-Only`): the full nonce-based
   policy (`default-src`, nonce'd `script-src`, `connect-src`, `img-src`, …). Browsers
   report violations without blocking, so we tune the allowlist against real traffic.

The report-only policy carries a `{{CSP_NONCE}}` placeholder token in config; middleware
replaces it with a fresh per-request nonce before sending the response.

### Flip to enforce (runbook)

1. Confirm report-only headers carry a fresh `nonce=…` and Next attaches it to its
   scripts.
2. Run the critical E2E paths (browse → cart → checkout → **card widget** on customer;
   listing create + **QR scan** on vendor; dashboards on admin). Collect
   `Content-Security-Policy-Report-Only` violations (browser console / report endpoint).
3. Widen the report-only allowlist only for legitimate origins; never add
   `'unsafe-inline'`/`'unsafe-eval'` to `script-src`.
4. When violations are clean, move the report-only directives into the enforced
   `Content-Security-Policy` header (i.e. promote the `buildReportOnlyCsp` output to the
   enforced header) and drop `Content-Security-Policy-Report-Only`.
5. Re-run Mozilla Observatory on each origin; expect grade A.

---

## 2. Policy per origin

Common to all three apps: `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Cross-Origin-Opener-Policy: same-origin`.

### Customer (`apps/customer`)

- `X-Frame-Options: SAMEORIGIN`, CSP `frame-ancestors 'self'`.
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()`.
- CSP allowlist: `self`, Cloudinary (`res.cloudinary.com`, images), Supabase
  (`*.supabase.co` + `wss://*.supabase.co`, connect), GA4
  (`*.googletagmanager.com` / `*.google-analytics.com` — allowed now; **M16-P05** wires
  the actual tag).
- **Lenco hosted card widget** (`pay.lenco.co` + `pay.sandbox.lenco.co` in
  `script-src`/`frame-src`/`connect-src`, plus `api.lenco.co` in `connect-src`) is added
  **only** on the checkout card route `/:locale/checkout/card/:paymentId`. Every other
  route's CSP omits Lenco. A negative-lookahead source
  (`/((?!.*checkout/card/).*)`) keeps the global (Lenco-free) report-only CSP off the
  card route so the two CSP headers are not intersected.

### Vendor (`apps/vendor`)

- `X-Frame-Options: SAMEORIGIN`, CSP `frame-ancestors 'self'`. No Lenco (payouts use the
  API, not the hosted widget).
- **Camera scoped to the QR scanner**: `camera=()` everywhere except the scanner routes
  `/:locale/scan` and `/:locale/events/:id/scan`, which get `camera=(self)`. The default
  rule excludes scan routes via lookahead so the two Permissions-Policy values are not
  intersected.

### Admin (`apps/admin`) — STRICTEST

- `X-Frame-Options: DENY`, CSP **`frame-ancestors 'none'`** (never framed),
  `frame-src 'none'`.
- No Lenco, **no GA4 / no third-party script or frame origins** — `script-src` is
  `'self' 'strict-dynamic' 'nonce-…'` only.
- Permissions-Policy denies every powerful feature (camera, mic, geolocation, payment,
  usb, sensors …).
- Additional `Cross-Origin-Resource-Policy: same-origin`. Layered behind the D20 IP
  allowlist + Cloudflare Access origin (see `docs/ops/admin-access.md`).

### Edge origins (`infra/Caddyfile`)

- Baseline snippet `(common_security)`: HSTS + nosniff + Referrer-Policy + COOP, and
  strips `Server`.
- `(api_security)` (API origin): strict — `X-Frame-Options DENY`, deny-all
  Permissions-Policy, and a locked CSP `default-src 'none'; frame-ancestors 'none';
base-uri 'none'; form-action 'none'` (API returns JSON only). No `Cross-Origin-Resource-Policy`
  so the cross-origin customer→API fetch (governed by FastAPI CORS) is not broken.
- `(hardened_edge)` (admin + n8n origins): baseline + `X-Frame-Options DENY` +
  deny-all Permissions-Policy + `Cross-Origin-Resource-Policy: same-origin`. The admin
  Next app additionally sends its own `frame-ancestors 'none'` CSP (defense in depth).
- Vendor origin imports only `(common_security)` — the vendor Next app owns CSP,
  Permissions-Policy (scanner camera) and X-Frame-Options; the edge must not overwrite them.

---

## 3. Header-check CI script

`scripts/ci/check-headers.mjs` statically asserts (against the config source, not a live
server) that each origin declares the required headers and CSP directives, that
`script-src` carries a nonce + `strict-dynamic` and no `unsafe-inline`, that admin is
`frame-ancestors 'none'`, and that the **Lenco allowance appears only on the customer
checkout card route** (and nowhere in vendor/admin/edge configs).

Run:

```sh
node scripts/ci/check-headers.mjs
```

Exit code is non-zero on any missing header/directive or Lenco leak. The converger wires
this into `.github/workflows/ci.yml` (M15-P05 owns `ci.yml` this wave).
