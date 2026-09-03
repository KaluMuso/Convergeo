#!/usr/bin/env node
// @ts-nocheck — plain-JS deploy-time probe, mirrors scripts/ci/e2e-staging-probe.mjs's style.
/**
 * Browser-based proof that the stable same-site Customer staging hostname
 * (e.g. customer.staging.vergeo5.com — see
 * docs/ops/staging-samesite-guest-cart.md) preserves guest-cart identity
 * across GET /cart -> POST /cart/items -> GET /cart, with the real
 * SameSite=Lax `vergeo_guest_cart` cookie genuinely attached by the BROWSER.
 *
 * Why a browser and not curl/fetch-from-Node: SameSite enforcement is a
 * browser cookie-jar policy tied to the REQUESTING PAGE's site, not
 * something a bare HTTP client has any concept of. Run #62 proved the
 * defect (POST 200, then a follow-up GET with no Cookie header at all) was
 * only ever visible through real Playwright browser traces — a curl/fetch
 * probe issued from Node has no "page" and would send whatever headers it's
 * told to, proving nothing about SameSite. So the two cart round-trips here
 * run as `fetch(..., {credentials:"include"})` INSIDE the page's own JS
 * context (`page.evaluate`), exactly like the real Customer app's client
 * code — and the actual outgoing Cookie header is independently observed at
 * the network layer via `page.on("request")` + `request.allHeaders()`
 * (async — Playwright's synchronous `request.headers()` deliberately omits
 * Cookie and other security-related headers; see
 * customer-stable-cart-probe-lib.mjs's `createCookieObserver` for the full
 * contract, including how the resulting request-event race is closed).
 * Unaffected by HttpOnly either way (that only blocks page JS from reading
 * `document.cookie`, not this Node-side network inspection).
 *
 * Add-to-Cart itself reuses the real PDP page: navigate to the seeded
 * product's PDP, handle the pickup-location picker exactly as
 * e2e/fixtures/add-to-cart.ts does, then click the real "Add to Cart"
 * button — so the POST /cart/items payload (listing_id, pickup_location_id,
 * qty) is constructed by the app's own proven client code, never
 * reconstructed here.
 *
 * Vercel Deployment Protection: the stable hostname aliases the SAME
 * Preview deployment the existing per-portal Preview-URL proof already
 * authenticates against (scripts/ci/vercel-staging-preview-prove.sh), so it
 * is not assumed unprotected. Reuses that SAME per-project "Protection
 * Bypass for Automation" secret — VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER,
 * falling back to VERCEL_AUTOMATION_BYPASS_SECRET — via
 * scripts/ci/e2e-staging-probe.mjs's `resolveBypassSecret()`, the same
 * precedence helper deploy-staging.yml's customer preflight already uses,
 * so this never invents or duplicates the resolution logic. (Not imported
 * from e2e/fixtures/env.ts: that module's own internal import of
 * ./seed.generated has no file extension, which resolves fine under the
 * Playwright Test runner's TS transform but NOT under this script's plain
 * `node --experimental-strip-types`, which requires explicit extensions —
 * scripts/ci/e2e-staging-probe.mjs is plain .mjs with zero imports, so it
 * has no such resolution issue.) Injected via `context.route()` on every request to
 * the STABLE HOSTNAME ONLY (never the API origin) — the exact mechanism
 * e2e/fixtures/test-base.ts's `portalBypass` auto-fixture already uses for
 * the real Playwright Test suite, reused here since this script runs
 * outside the Test runner and so does not get that fixture for free. Using
 * `request.headers()` (sync, no Cookie) to build the passthrough header set
 * for `route.fallback({headers})` is safe and unrelated to the bug above:
 * Playwright ignores any Cookie key passed through that path and always
 * lets the browser's real cookie jar govern the actual Cookie header sent —
 * which is *why* `.headers()` omits it in the first place. The secret is
 * never logged, never placed in a URL/argv/evidence, and never captured to
 * a trace (this script never calls `context.tracing.start()`).
 * `page.goto()`'s landed URL is checked against the expected hostname
 * (`detectProtectionChallenge`) and fails closed if the bypass didn't work —
 * a redirect to a Vercel login page is never treated as "the app is down".
 *
 * Opt-in only: this only runs once CUSTOMER_STAGING_STABLE_URL is
 * configured. The hostname is not provisioned yet as of this script's
 * introduction (DNS + Vercel custom-domain are one-time operator actions —
 * see the doc above), so by default this prints SKIPPED and exits 0.
 * deploy-staging.yml never fails because of this file until an operator
 * opts in by setting the var.
 *
 * Usage (from e2e/, after `npm ci`):
 *   node --experimental-strip-types scripts/customer-stable-cart-probe.mjs
 *   node --experimental-strip-types scripts/customer-stable-cart-probe.mjs --dry-run
 *
 * --experimental-strip-types is required because SEED.product.slug is read
 * from the generated .ts fixture (fixtures/seed.generated.ts) — the same
 * flag ci.yml already uses for the other self-tests that import a .ts
 * module (see scripts/ci/test-staging-guards.sh's check for this).
 *
 * Env:
 *   CUSTOMER_STAGING_STABLE_URL        e.g. https://customer.staging.vergeo5.com
 *   CUSTOMER_STAGING_API_URL           e.g. https://api.staging.vergeo5.com
 *                                       (falls back to STAGING_API_BASE_URL,
 *                                       then https://${STAGING_API_HOST})
 *   VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER / VERCEL_AUTOMATION_BYPASS_SECRET
 *                                       Deployment Protection bypass (same
 *                                       precedence as the rest of e2e/)
 *   E2E_LOCALE                         default "en"
 */

import { chromium } from "@playwright/test";

import { resolveBypassSecret } from "../../scripts/ci/e2e-staging-probe.mjs";
import { SEED } from "../fixtures/seed.generated.ts";
import {
  assertSameSite,
  buildPdpPath,
  createCookieObserver,
  detectProtectionChallenge,
  evaluateCartIdentity,
  evaluateCookieEvidence,
  parseStableOrigin,
} from "./customer-stable-cart-probe-lib.mjs";

/** Same precedence as every other customer-portal bypass resolution in this repo. */
const CUSTOMER_BYPASS_VARS = [
  "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
  "VERCEL_AUTOMATION_BYPASS_SECRET",
];

function resolveCustomerBypassSecret() {
  return resolveBypassSecret(process.env, { bypassVars: CUSTOMER_BYPASS_VARS }).secret;
}

function log(msg) {
  console.log(`==> [customer-stable-cart-probe] ${msg}`);
}

async function fetchCart(page, apiOrigin) {
  return page.evaluate(async (origin) => {
    const res = await fetch(`${origin}/cart`, { credentials: "include" });
    let body = null;
    try {
      body = await res.json();
    } catch {
      // non-JSON — surfaced via status below
    }
    return { status: res.status, body };
  }, apiOrigin);
}

/**
 * @param {{
 *   stableUrlRaw: string,
 *   apiBaseRaw: string,
 *   locale?: string,
 *   slug?: string,
 *   bypassSecret?: string,
 *   launchBrowser?: () => Promise<import("@playwright/test").Browser>,
 * }} args
 */
export async function runProbe({
  stableUrlRaw,
  apiBaseRaw,
  locale = "en",
  slug = SEED.product.slug,
  bypassSecret = resolveCustomerBypassSecret(),
  launchBrowser = () => chromium.launch(),
}) {
  const originResult = parseStableOrigin(stableUrlRaw, "CUSTOMER_STAGING_STABLE_URL");
  if (!originResult.ok) {
    return { verdict: originResult.missing ? "SKIPPED" : "FAIL", detail: originResult.reason };
  }

  const apiResult = parseStableOrigin(apiBaseRaw, "CUSTOMER_STAGING_API_URL");
  if (!apiResult.ok) {
    return { verdict: "FAIL", detail: apiResult.reason };
  }

  const site = assertSameSite(originResult.hostname, apiResult.hostname);
  if (!site.same) {
    return {
      verdict: "FAIL",
      detail:
        `CUSTOMER_STAGING_STABLE_URL (site=${site.customerSite}) and CUSTOMER_STAGING_API_URL ` +
        `(site=${site.apiSite}) are not same-site — SameSite=Lax cannot survive this topology, ` +
        "so this probe would prove nothing by running",
    };
  }

  log(`stable origin=${originResult.origin} api origin=${apiResult.origin} slug=${slug}`);
  log(
    bypassSecret
      ? "Deployment Protection bypass: configured (source name only, never the value, is ever logged)"
      : "Deployment Protection bypass: none configured — the stable hostname must already be reachable without one",
  );

  const browser = await launchBrowser();
  try {
    const context = await browser.newContext();

    // See the file header for why this is safe and distinct from the
    // Cookie-observation fix above.
    if (bypassSecret) {
      await context.route("**/*", async (route) => {
        const reqUrl = route.request().url();
        if (!reqUrl.startsWith(originResult.origin)) {
          await route.fallback();
          return;
        }
        await route.fallback({
          headers: {
            ...route.request().headers(),
            "x-vercel-protection-bypass": bypassSecret,
            "x-vercel-set-bypass-cookie": "true",
          },
        });
      });
    }

    const page = await context.newPage();

    const cookieObserver = createCookieObserver({ apiOrigin: apiResult.origin });
    page.on("request", cookieObserver.handleRequest);

    const navigationResponse = await page.goto(
      `${originResult.origin}${buildPdpPath(locale, slug)}`,
      { waitUntil: "domcontentloaded" },
    );

    const landedUrl = navigationResponse ? navigationResponse.url() : page.url();
    const challenge = detectProtectionChallenge(landedUrl, originResult.origin);
    if (challenge.blocked) {
      return { verdict: "FAIL", detail: `BLOCKED_EXTERNAL: ${challenge.reason}` };
    }

    const initial = await fetchCart(page, apiResult.origin);
    log(`initial GET /cart -> HTTP ${initial.status} cart_id=${initial.body?.cart_id ?? "<none>"}`);

    // Mirrors e2e/fixtures/add-to-cart.ts: a branch-tracked listing requires
    // an explicit pickup branch before Add to Cart is enabled. Never inject
    // pickup_location_id directly — that would test a different, API-level
    // contract instead of the real Customer journey this probe exists to
    // prove.
    const pickupSelect = page.getByTestId("pdp-pickup-location-select");
    const pickupRequired = await pickupSelect
      .waitFor({ state: "visible", timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    if (pickupRequired) {
      const branchOptions = await pickupSelect.locator("option:not([value=''])").allTextContents();
      if (branchOptions.length === 0) {
        return {
          verdict: "FAIL",
          detail: "pdp-pickup-location-select rendered with no selectable branch — cannot proceed",
        };
      }
      await pickupSelect.selectOption({ index: 1 });
    }

    const cartItemsResponsePromise = page
      .waitForResponse(
        (res) => res.request().method() === "POST" && res.url().includes("/cart/items"),
        { timeout: 15_000 },
      )
      .catch(() => null);

    await page.getByTestId("pdp-add-to-cart").click();

    const cartItemsResponse = await cartItemsResponsePromise;
    if (!cartItemsResponse) {
      return {
        verdict: "FAIL",
        detail: "no POST /cart/items response observed after clicking Add to Cart",
      };
    }
    const postItemsStatus = cartItemsResponse.status();
    const postItemsBody = await cartItemsResponse.json().catch(() => null);
    log(
      `POST /cart/items -> HTTP ${postItemsStatus} cart_id=${postItemsBody?.cart_id ?? "<none>"}`,
    );
    if (postItemsStatus !== 200 || !postItemsBody) {
      return { verdict: "FAIL", detail: `POST /cart/items returned HTTP ${postItemsStatus}` };
    }

    const final = await fetchCart(page, apiResult.origin);
    log(`final GET /cart -> HTTP ${final.status} cart_id=${final.body?.cart_id ?? "<none>"}`);
    if (final.status !== 200 || !final.body) {
      return { verdict: "FAIL", detail: `final GET /cart returned HTTP ${final.status}` };
    }

    const addedItems = Array.isArray(postItemsBody.items) ? postItemsBody.items : [];
    const addedListingId =
      addedItems.length > 0 ? addedItems[addedItems.length - 1]?.listing_id : undefined;
    const finalItems = Array.isArray(final.body.items) ? final.body.items : [];
    const addedListingPresent = Boolean(
      addedListingId && finalItems.some((item) => item.listing_id === addedListingId),
    );

    const identity = evaluateCartIdentity({
      initialCartId: initial.body?.cart_id ?? "",
      postItemsCartId: postItemsBody.cart_id ?? "",
      finalCartId: final.body.cart_id ?? "",
      addedListingPresent,
    });

    // Closes the request-event race documented on createCookieObserver: the
    // POST and final GET have both already completed above, so every header
    // check they triggered has been pushed — awaiting them here is
    // guaranteed to see the complete set before evaluateCookieEvidence reads it.
    await cookieObserver.waitForPending();
    const cookies = evaluateCookieEvidence(cookieObserver.seen);

    if (!identity.ok || !cookies.ok) {
      const problems = [...identity.problems];
      if (!cookies.ok) {
        problems.push(`Cookie header not observed on: ${cookies.missing.join(", ")}`);
      }
      return { verdict: "FAIL", detail: problems.join("; "), identity, cookies };
    }

    return {
      verdict: "PASS",
      detail:
        "guest-cart identity persisted across GET/POST/GET with the Cookie header attached on " +
        "the same-site stable hostname",
      identity,
      cookies,
    };
  } finally {
    await browser.close();
  }
}

async function main() {
  const dryRun = process.argv.includes("--dry-run");
  const stableUrlRaw = process.env.CUSTOMER_STAGING_STABLE_URL ?? "";
  const apiBaseRaw =
    process.env.CUSTOMER_STAGING_API_URL ||
    process.env.STAGING_API_BASE_URL ||
    (process.env.STAGING_API_HOST ? `https://${process.env.STAGING_API_HOST}` : "");
  const locale = (process.env.E2E_LOCALE || "en").trim() || "en";

  if (!stableUrlRaw.trim()) {
    console.log(
      JSON.stringify({
        verdict: "SKIPPED",
        detail:
          "CUSTOMER_STAGING_STABLE_URL not set — stable-hostname cart probe not configured yet",
      }),
    );
    process.exit(0);
  }

  if (dryRun) {
    const originResult = parseStableOrigin(stableUrlRaw, "CUSTOMER_STAGING_STABLE_URL");
    const apiResult = parseStableOrigin(apiBaseRaw, "CUSTOMER_STAGING_API_URL");
    if (!originResult.ok || !apiResult.ok) {
      console.error(`::error::${originResult.ok ? apiResult.reason : originResult.reason}`);
      process.exit(1);
    }
    const site = assertSameSite(originResult.hostname, apiResult.hostname);
    if (!site.same) {
      console.error(
        `::error::CUSTOMER_STAGING_STABLE_URL (${site.customerSite}) and CUSTOMER_STAGING_API_URL ` +
          `(${site.apiSite}) are not same-site`,
      );
      process.exit(1);
    }
    console.log(
      JSON.stringify({
        verdict: "DRY_RUN_OK",
        origin: originResult.origin,
        apiOrigin: apiResult.origin,
        site: site.customerSite,
      }),
    );
    process.exit(0);
  }

  const result = await runProbe({ stableUrlRaw, apiBaseRaw, locale });
  console.log(JSON.stringify({ verdict: result.verdict, detail: result.detail }));
  if (result.verdict === "FAIL") {
    console.error(`::error::customer-stable-cart-probe FAIL — ${result.detail}`);
    process.exit(1);
  }
  if (result.verdict === "SKIPPED") {
    console.warn(`::warning::customer-stable-cart-probe SKIPPED — ${result.detail}`);
  }
  process.exit(0);
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"));

if (isMain) {
  main().catch((err) => {
    console.error(
      `::error::customer-stable-cart-probe crashed: ${err instanceof Error ? err.message : err}`,
    );
    process.exit(1);
  });
}
