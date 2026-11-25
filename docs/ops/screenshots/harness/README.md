# Screenshot harness

Signed-in screenshots of the customer, vendor and admin apps without a real Supabase project or API.

`mock-backend.mjs` is a loopback-only stand-in for Supabase Auth and the Convergeo API. It serves an RS256 JWKS and `/auth/v1/user` the same way `packages/auth/src/session-routing.integration.test.ts` does, so the real `@supabase/ssr` SDK verifies the session cookie and the portal middleware gates run unchanged. API responses come from `fixtures-{customer,vendor,admin}.mjs` (money in ngwee). Nothing here is used by the apps at build or run time.

## Run

Start each app's dev server pointed at its fixture port (one port per app so captures can run side by side):

```bash
# customer → 54331, vendor → 54332, admin → 54333
P=54332  # vendor
NEXT_PUBLIC_DEPLOYMENT_PLANE=development \
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:$P NEXT_PUBLIC_SUPABASE_ANON_KEY=local-screenshot-fixture \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$P NEXT_PUBLIC_VERGEO_API_URL=http://127.0.0.1:$P \
NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=convergeo \
NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS=0 NEXT_PUBLIC_VENDOR_PAYOUTS_ENABLED=true \
pnpm --filter vendor dev
```

Then, from the repo root (the capture starts the fixture backend itself):

```bash
node docs/ops/screenshots/harness/capture.mjs vendor            # every route, 360/1280 × light/dark
QUICK=1 node docs/ops/screenshots/harness/capture.mjs vendor orders   # one route, 1280 light only
```

Output is WebP (≤80 KB, ≤1280 px wide) in `docs/ops/screenshots/<task>/`. The script exits non-zero and lists problems when a route redirects (for example to login), the browser logs a console error, the Next.js dev overlay shows an issue, or the page calls an API path that has no fixture. The idle Next.js dev-tools button is removed before each shot only when it shows no issues.

`home-empty` answers every API call with 404 to show the customer home when the catalogue is empty or the API is down.
