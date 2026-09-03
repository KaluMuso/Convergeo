# Staging guest-cart SameSite remediation (Run #62)

## Proven root cause

Run #62's real Playwright browser traces proved: `POST /cart/items` returns
`200` with the added item in the response body, but the immediately-following
`GET /cart` comes back as a **brand-new, empty cart** — with no
`vergeo_guest_cart` Cookie request header on the follow-up request at all.

The API sets `vergeo_guest_cart` as `HttpOnly` + `Secure` +
`SameSite=Lax` (`services/api/app/routers/cart.py`'s `_set_guest_cookie`).
Today's certified staging Customer surface is a Vercel Preview deployment on
`*.vercel.app`; the staging API is `api.staging.vergeo5.com`. Those two
hostnames do **not** share a registrable domain (`vercel.app` vs.
`vergeo5.com`), so a credentialed `fetch()` from the Preview origin to the API
is **cross-site**, and `SameSite=Lax` correctly refuses to attach the cookie
on that follow-up `GET` — the browser is behaving exactly as designed.

This is not an Add-to-Cart bug, a CORS bug, a cart selector/timeout issue, or
an API persistence defect. It is a topology mismatch: the certified staging
Preview surface is cross-site with the staging API, and no `SameSite=Lax`
cookie can survive that.

Production does **not** have this problem: the Customer app is
`vergeo5.com`/`www.vergeo5.com` and the API is `api.vergeo5.com` — both under
the `vergeo5.com` registrable domain, so guest-cart cookies are same-site
there today. The fix below is exactly that production topology, reproduced
for staging.

## 1. Audit — what already exists vs. what's missing

Primary evidence: `infra/ENVIRONMENTS.md`, `infra/vercel.md`,
`infra/cloudflare-dns.md` (pre-this-doc contents), `infra/staging/.env.staging.example`.

| Piece                                                                                                | Status                                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Separate Vercel _projects_ per staging portal                                                        | Not needed — staging already uses branch-scoped Preview config on the SAME three projects (`convergeo-customer/-vendor/-admin`), per `infra/vercel.md` §"Staging Preview (branch `staging`)".                                    |
| `customer.staging.vergeo5.com` DNS record                                                            | **Does not exist.** Not even listed as "optional" in `infra/cloudflare-dns.md`'s staging table (unlike `vendor.staging`/`admin.staging`, which were already documented as optional-and-unprovisioned).                           |
| `customer.staging.vergeo5.com` as a Vercel custom domain on `convergeo-customer`                     | **Does not exist.** `infra/vercel.md` §"Domains" lists only `vergeo5.com`/`www.vergeo5.com` (production) and `*.vercel.app` (Preview) for that project.                                                                          |
| `api.staging.vergeo5.com`                                                                            | Exists and is live (OCI, `vergeo5-api-staging` container). Registrable domain: `vergeo5.com`.                                                                                                                                    |
| A mechanism to keep a stable hostname pointed at the exact candidate-SHA deployment on every release | **Does not exist.** `deploy-staging.yml` has no alias/domain step anywhere (confirmed by search); the closest analogue (`vendor.staging`/`admin.staging`) is documented as "optional" with no automation either.                 |
| `E2E_BASE_URL` (the repo secret Playwright's strict suite targets)                                   | Today an operator-maintained secret pointed at the current Preview URL — i.e. exactly the "someone manually clicking a different deployment" pattern this remediation is meant to end, once the stable hostname exists (see §6). |

**Conclusion: nothing is provisioned for a stable Customer staging hostname.**
Two operator actions are required before this fix is live — see §6.

## 2. Chosen architecture: stable same-site custom hostname

**`customer.staging.vergeo5.com` (Vercel custom domain, aliased to the
candidate-SHA Preview deployment) + `api.staging.vergeo5.com` (unchanged).**

This is production parity, not a new pattern: production's
`vergeo5.com`↔`api.vergeo5.com` relationship is exactly this shape already.
It preserves `Secure`/`HttpOnly`/`SameSite=Lax` on the guest-cart cookie
unchanged and needs no third-party-cookie allowance.

Rejected alternatives:

- **`SameSite=None`** — explicitly forbidden by this task's constraints, and
  it would also require reworking `Secure` handling and expose the cookie to
  strictly weaker cross-site attachment rules for a defect that has a
  same-site fix available. Not chosen.
- **Same-origin frontend BFF/proxy** (customer app proxies `/cart/*` to the
  API under its own origin) — makes the app itself the cross-origin hop
  instead, adds a new runtime component (reverse proxy config, an extra point
  of failure, latency), and diverges from how every other Vergeo5 API call
  already works (direct `NEXT_PUBLIC_API_BASE_URL` calls). Bigger blast
  radius for the same outcome a DNS record + Vercel domain achieves. Not
  chosen.
- **Explicit guest-cart token** (e.g. a `X-Guest-Cart-Token` header instead of
  a cookie) — a real API/frontend contract change (new header plumbing,
  client-side storage, a second identity mechanism to keep in sync with the
  cookie path production already uses). Diverges from production's actual
  cookie-based mechanism, so staging would stop proving what production does.
  Not chosen.

## 3. CORS

No code change: `services/api/app/settings.py`'s `CORS_ORIGINS` (an operator
env var on the OCI staging container, `infra/staging/.env`) already accepts
arbitrary exact origins alongside the staging-only immutable-Preview regex
(`STAGING_PREVIEW_ORIGIN_REGEX`, unrelated and untouched). Once the hostname
is provisioned, an operator adds it there — see §6 and the updated comment in
`infra/staging/.env.staging.example`.

`scripts/ci/staging-cors-preview-probe.sh` gained an optional
`--extra-origin` flag (repeatable) that runs the _same_ preflight assertion
(`Access-Control-Allow-Origin` reflects the exact origin,
`Access-Control-Allow-Credentials: true`) the three Preview origins already
get. `deploy-staging.yml`'s CORS proof step passes
`--extra-origin https://${{ vars.CUSTOMER_STAGING_STABLE_HOSTNAME }}` only
when that variable is set — a pure no-op otherwise. Both the immutable
Preview origins and the stable hostname are proven every deploy; neither
replaces the other.

## 4. Deployment model

`scripts/ci/vercel-staging-preview-prove.sh` (the script `deploy-staging.yml`'s
`prove-vercel-preview` job already runs per portal, per candidate SHA) gained
an opt-in step, customer-portal-only: once the existing health/fingerprint
check has already proven `deployment_id` serves `GITHUB_SHA`, and
`CUSTOMER_STAGING_STABLE_HOSTNAME` is configured, it calls the Vercel API
(`POST /v2/deployments/{deployment_id}/aliases`) to point that exact hostname
at that exact deployment. This is **fail-closed once configured**: if the
alias call fails (e.g. the domain hasn't been added to the Vercel project
yet), the whole job fails — a staging release can never silently leave the
stable hostname pointed at a stale or wrong deployment. Absent the variable,
this step is a complete no-op and today's behavior (Preview-URL-only) is
unchanged.

The evidence chain deploy-staging.yml already produces now carries the extra
link end to end:

```
candidate SHA (GITHUB_SHA)
  -> Customer deployment_id (Vercel API create-deployment response)
  -> preview_url (proven READY, commit_sha == GITHUB_SHA, health/fingerprint verified)
  -> stable_hostname_url (Vercel alias-assign response confirms the alias == the configured hostname)
  -> same deployment_id throughout
```

recorded in `evidence.json`'s new `stable_hostname_status`
(`"not_configured"` | `"aliased"`) and `stable_hostname_url` fields, and
exposed as step outputs.

**This means release certification never depends on an operator manually
selecting a deployment in the Vercel dashboard** — once the one-time setup in
§6 is done, every staging push re-proves and re-aliases automatically.

## 5. Cart live probe

`e2e/scripts/customer-stable-cart-probe.mjs` (new) is a real-**browser**
proof — not curl/fetch-from-Node, which has no SameSite/cookie-jar policy to
prove anything with. It launches Chromium, navigates the seeded product's PDP
on the stable hostname, and:

1. `fetch(apiOrigin + "/cart", {credentials:"include"})` from **inside the
   page's own JS context** (`page.evaluate`) — exactly what the real Customer
   app's client code does, so the browser applies its genuine SameSite policy
   (a Node-side `fetch()` or `page.request` call would not; see the script's
   header comment for why that distinction matters here).
2. Clicks the real `pdp-add-to-cart` button (handling the pickup-location
   picker exactly as `e2e/fixtures/add-to-cart.ts` does) — so `POST
/cart/items`'s payload is built by the app's own proven client code, never
   reconstructed in this script.
3. Repeats step 1.

It asserts: the `cart_id` from `POST /cart/items` and the follow-up `GET
/cart` are identical (same guest-cart identity — divergence here is exactly
the Run #62 symptom, a brand-new empty cart); the added `listing_id` is
present in the final cart; and — independently, via `page.on("request")`
reading Chromium's actual outgoing headers, which sees the real Cookie header
regardless of `HttpOnly` — that a `Cookie` header was genuinely sent on both
requests.

Pure logic (URL/site validation, the identity and cookie assertions) lives in
`e2e/scripts/customer-stable-cart-probe-lib.mjs` with no Playwright import, so
it's unit-tested from the repo root
(`scripts/qa/self-test/customer-stable-cart-probe-lib.test.mjs`, 19 cases)
without an `e2e/` install. The full browser script is opt-in via
`CUSTOMER_STAGING_STABLE_URL` (SKIPPED, exit 0, when unset) and wired into
`deploy-staging.yml`'s `smoke` job the same way as the alias/CORS steps —
Node + Chromium install only happen when the variable is configured.

**Not yet run against a live target** in this PR's verification pass: the
hostname does not exist yet (§1). What _is_ verified now: all 19 unit tests
pass, and `--dry-run` correctly validates same-site config, rejects a
`*.vercel.app` value, and rejects a cross-site API pairing — see the PR's
`TESTS` section.

## 6. One-time operator setup (this PR cannot perform)

1. **DNS** (Cloudflare, `vergeo5.com` zone): add `customer.staging` as a
   `CNAME` to `cname.vercel-dns.com`, proxied — see the updated row in
   `infra/cloudflare-dns.md`.
2. **Vercel**: add `customer.staging.vergeo5.com` as a custom domain on the
   `convergeo-customer` project (Project → Settings → Domains). Do not assign
   it to a specific Git branch there — the alias step in
   `vercel-staging-preview-prove.sh` re-points it explicitly on every deploy,
   which is the fail-closed, SHA-proven path this doc describes.
3. **API CORS**: add `https://customer.staging.vergeo5.com` to `CORS_ORIGINS`
   in the staging OCI container's `infra/.env`, then `docker compose up -d
api` (per `infra/ENVIRONMENTS.md` conventions — edit-then-recreate, not a
   bare restart).
4. **GitHub**: set the repository or `staging`-environment **Variable** (not
   Secret) `CUSTOMER_STAGING_STABLE_HOSTNAME=customer.staging.vergeo5.com`.
   The next `deploy-staging.yml` run on `staging` will alias the hostname,
   prove its CORS support, and run the browser cart probe automatically.
5. Once a deploy has gone green with the variable set, rotate the
   `E2E_BASE_URL` repository secret to `https://customer.staging.vergeo5.com`
   so the strict 65-test suite (`e2e.yml`) certifies against the stable,
   same-site target instead of a Preview URL that has to be hand-copied per
   release. `E2E_VENDOR_BASE_URL`/vendor's own Preview URL is unaffected —
   per this remediation's scope, Vendor stays on its immutable Preview URL
   (Section 6 of the originating task: no other same-site requirement exists
   for Vendor today). This is deliberately **not** done by this PR — the
   hostname isn't live yet, and flipping a certification secret ahead of a
   live target would break the very suite it's meant to protect.

Until step 4 is done, every change in this PR is inert and today's staging
pipeline behaves exactly as before.
