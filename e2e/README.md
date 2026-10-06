# Vergeo5 E2E suite (Playwright)

End-to-end coverage of the critical paths, run on a **Fast-3G / 360px** mobile
project (Chromium). This is a **standalone package** (`@vergeo/e2e`) — it is NOT
part of the pnpm workspace and has its own `package.json` / lockfile-free install
so it never perturbs app builds.

## Specs (critical paths)

| Spec                     | Path                                                                                                | Founder/staging-gated legs                                                                           |
| ------------------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `checkout-false-success` | pending/failed/unknown/COD/card honesty — **never** render unpaid as paid (S6/G4)                   | default **payment-mock** (CI); live pay not required                                                 |
| `critical-path`          | locale home → browse/search → PDP/cart → checkout branch matching env (G16)                         | sandbox MoMo settle (`E2E_DEPLOYED_TARGET` + `LENCO_SANDBOX`)                                        |
| `shop-checkout-momo`     | browse → search → PDP → cart → checkout → **MoMo pay** → confirmation → WhatsApp receipt            | Lenco sandbox charge (`LENCO_SANDBOX`), WhatsApp assertion (`WHATSAPP_MOCK`)                         |
| `shop-cod`               | PDP → cart → checkout → **Cash-on-Delivery** → confirmation                                         | none (runs on any live target)                                                                       |
| `vendor-sell`            | approved vendor → list → receive order → **ship**                                                   | vendor OTP session (`E2E_TEST_PHONE`/`E2E_TEST_OTP`)                                                 |
| `event-ticket`           | paid order → issued wallet ticket → **admission + duplicate rejection**; independent free RSVP scan | paid path (sandbox, buyer/vendor OTP, RLS read keys); free RSVP scan (vendor OTP + `E2E_TICKET_PIN`) |
| `auth-otp`               | phone → request OTP → **verify → signed in**                                                        | verify leg (`E2E_TEST_PHONE`/`E2E_TEST_OTP`)                                                         |

A missing paid-ticket prerequisite **fails** integrated-staging and production-readiness certification. Local runs skip with an annotation. The paid provider leg also requires explicit `E2E_PAID_TICKET_PROVIDER_APPROVED=1`; the hosted workflow does not set it, so routine scheduled and diagnostic runs cannot start this new charge. No provider charge is attempted when the gate is closed. No credentials are committed; all come from env/secrets.

## Environment variables

| Var                                                                           | Purpose                                                                                                                                                                |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `E2E_BASE_URL`                                                                | Customer app origin (staging deploy or `http://localhost:3000`).                                                                                                       |
| `VERCEL_AUTOMATION_BYPASS_SECRET`                                             | Vercel Deployment Protection bypass header for SSO-gated Preview URLs (CI secret; never commit).                                                                       |
| `E2E_EXPECT_SHA` / `E2E_STRICT_SHA`                                           | Optional release-candidate SHA proof against `/health` `buildId` (strict in pre-release / integrated-staging).                                                         |
| `E2E_VENDOR_BASE_URL` / `E2E_ADMIN_BASE_URL`                                  | Separate app origins. Default to customer for convenience — but in a strict certification run an unset/collapsed `E2E_VENDOR_BASE_URL` **fails**, it never falls back. |
| `E2E_LOCALE`                                                                  | Locale segment for `[locale]/` routing (default `en`).                                                                                                                 |
| `E2E_THROTTLE`                                                                | `0` disables Fast-3G throttling (default on).                                                                                                                          |
| `E2E_PAYMENT_MOCK`                                                            | Force deterministic `/payments/status` + card-verify mocks (default on when sandbox creds absent).                                                                     |
| `E2E_DEPLOYED_TARGET`                                                         | Prefer live target behaviour for critical-path settle (still requires sandbox creds for pay).                                                                          |
| `NEXT_PUBLIC_E2E_MOCK_SESSION`                                                | Customer app flag (`1`) enabling Playwright-injected buyer session for payment-mock specs. **Dev/CI only.**                                                            |
| `E2E_SEED_RESET_URL` / `E2E_SEED_TOKEN`                                       | Deterministic, idempotent seed reset (staging-only, token-guarded).                                                                                                    |
| `LENCO_SANDBOX` + `LENCO_SANDBOX_SECRET_KEY` / `_PUBLIC_KEY` / `_MOMO_NUMBER` | Enables the live Lenco sandbox pay leg (**founder gate F9b**).                                                                                                         |
| `WHATSAPP_MOCK` + `WHATSAPP_MOCK_OUTBOX_URL`                                  | Enables WhatsApp receipt assertions via the mock outbox.                                                                                                               |
| `E2E_TEST_PHONE` + `E2E_TEST_OTP`                                             | Deterministic OTP for the verify + vendor/organiser legs.                                                                                                              |
| `E2E_TICKET_PIN`                                                              | Private run-issued free RSVP scanner PIN. The paid test reads its own purchased ticket PIN from the buyer wallet.                                                      |
| `STAGING_SUPABASE_URL` + `STAGING_SUPABASE_ANON_KEY`                          | Authenticated, buyer-scoped, read-only RLS proof of paid order item → ticket linkage.                                                                                  |
| `E2E_PAID_TICKET_PROVIDER_APPROVED`                                           | Explicit, ticket-specific provider approval for a separately authorized run; absent from hosted workflow by default.                                                   |
| `PW_CHROMIUM_PATH`                                                            | Path to a pre-installed Chromium (skips download).                                                                                                                     |

## Run locally

```bash
cd e2e
npm install --no-package-lock          # installs @playwright/test 1.56.1

# Against a local customer dev server (pnpm --filter customer dev on :3000):
E2E_BASE_URL=http://localhost:3000 \
PW_CHROMIUM_PATH=/opt/pw-browsers/chromium \
  npx playwright test --project=mobile-390

# Six projects total (fixtures/spec-classification.ts is the source of truth for
# which spec runs on which): mobile-360/390/430, tablet-768, desktop-1440 (the
# certification viewports) and fast-3g (throttled, performance/byte-budget specs
# only). mobile-390 is canonical — most specs run there and nowhere else.

# Discover specs without launching a browser:
npx playwright test --list
```

The non-payment flows (`shop-cod`, and the un-gated boundaries of the others) run
against a local dev server with seed data. The gated legs require staging + the
secrets above.

## Run on staging (CI)

`.github/workflows/e2e.yml` runs **nightly** (`schedule`) and on demand
(`workflow_dispatch`, with a `pre_release` input) against `E2E_BASE_URL`
(staging environment `STAGING_CUSTOMER_URL` mirrored in repository secret
`E2E_BASE_URL`). Missing URL **fails the workflow** (never a vacuous green skip).
An identity-aware preflight probe (`scripts/ci/e2e-staging-probe.mjs <portal>`)
runs once per **directly-navigated** portal — `customer` and `vendor` — before
any browser is installed. Each verifies `/{locale}/health` on its own origin
(`status=ok`, expected `app`, `env ∈ {staging,preview}`, `buildId` against the
release-candidate SHA), rejects Vercel SSO interstitials as `BLOCKED_EXTERNAL`,
and uses that Vercel project's own bypass secret
(`VERCEL_AUTOMATION_BYPASS_SECRET_{CUSTOMER,VENDOR}`, falling back to the
repository-wide `VERCEL_AUTOMATION_BYPASS_SECRET`). Both read the same
`E2E_EXPECT_SHA`, so they cannot certify different candidates. There is
deliberately **no admin probe**: no spec navigates the admin origin, and Deploy
staging proves admin independently.

For a release-quality baseline, pass the **immutable** Preview URLs rather than
the mutable `-git-staging-` branch aliases:

```
base_url        = https://convergeo-customer-<id>-vergeo-projects.vercel.app
vendor_base_url = https://convergeo-vendor-<id>-vergeo-projects.vercel.app
expect_sha      = <exact staging SHA>
pre_release     = true
```

Playwright sends `x-vercel-protection-bypass` per origin (see
`e2e/fixtures/test-base.ts`).
It installs Chromium, runs the suite, and uploads trace/video artifacts on
failure. It is **not** a required per-PR gate (staging-dependent).

## Founder / staging gate (F9b)

The paid ticket acceptance test selects the canonical paid event type, captures its minted order and item, charges that exact group through the existing MoMo retry API, and requires a successful payment, issued ticket, matching event/instance/type, buyer wallet entry, and organiser admission of that same ticket. The free RSVP scanner test remains independent. The ticket picker redirects to `/checkout?group=…`; the companion checkout UI patch handles that group, while the acceptance helper charges the captured order through the existing payment API.

The **full-green run against deployed staging with a real Lenco sandbox charge**
requires a reachable staging deploy, Lenco sandbox credentials, and explicit
ticket-specific provider approval (`E2E_PAID_TICKET_PROVIDER_APPROVED=1`). The
deploy and credentials are the **F9b founder gate**, not available in the build
env; the hosted workflow does not inject approval. Until separately authorized,
source-only checks validate structure (`--list`, typecheck, and mocked contracts);
provider-backed paid admission remains unrun and strict certification fails
closed when its prerequisites are absent.
