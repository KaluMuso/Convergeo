/**
 * Pure helpers for scripts/customer-stable-cart-probe.mjs — no Playwright
 * import, so this file (and only this file) is unit-tested from the
 * repository root via plain `node --test`, without an `e2e/` npm install.
 * See scripts/qa/self-test/customer-stable-cart-probe-lib.test.mjs.
 */

/**
 * @param {string} raw
 * @param {string} varName
 * @returns {{ ok: true, origin: string, hostname: string } | { ok: false, reason: string, missing?: boolean }}
 */
export function parseStableOrigin(raw, varName) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) {
    return { ok: false, reason: `${varName} is not set`, missing: true };
  }
  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return { ok: false, reason: `${varName} is not a valid URL` };
  }
  if (url.protocol !== "https:") {
    return { ok: false, reason: `${varName} must use https` };
  }
  const hostname = url.hostname.toLowerCase();
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return { ok: false, reason: `${varName} must not be localhost` };
  }
  if (hostname.endsWith(".vercel.app")) {
    return {
      ok: false,
      reason:
        `${varName} must be the stable same-site hostname, not a *.vercel.app Preview URL — ` +
        "the cross-site Preview origin is exactly the case this probe exists to rule out (Run #62)",
    };
  }
  return { ok: true, origin: url.origin, hostname };
}

/**
 * Registrable-domain (eTLD+1) comparison. Vergeo5's hostnames are simple
 * two-label-suffix domains (vergeo5.com) — no multi-part public suffix
 * (e.g. co.uk) is in use anywhere in this repo's DNS, so "last two labels"
 * is a correct and sufficient site definition here; a general public-suffix
 * list is deliberately not pulled in for a comparison this narrow.
 *
 * @param {string} customerHostname
 * @param {string} apiHostname
 */
export function assertSameSite(customerHostname, apiHostname) {
  const site = (h) => h.toLowerCase().split(".").slice(-2).join(".");
  const customerSite = site(customerHostname);
  const apiSite = site(apiHostname);
  return { same: customerSite === apiSite, customerSite, apiSite };
}

/** @param {string} locale @param {string} slug */
export function buildPdpPath(locale, slug) {
  return `/${locale}/p/${slug}`;
}

/**
 * @param {{
 *   initialCartId: string,
 *   postItemsCartId: string,
 *   finalCartId: string,
 *   addedListingPresent: boolean,
 * }} args
 */
export function evaluateCartIdentity({
  initialCartId,
  postItemsCartId,
  finalCartId,
  addedListingPresent,
}) {
  /** @type {string[]} */
  const problems = [];
  if (!postItemsCartId) {
    problems.push("POST /cart/items response had no cart_id");
  }
  if (!finalCartId) {
    problems.push("final GET /cart response had no cart_id");
  }
  if (postItemsCartId && finalCartId && postItemsCartId !== finalCartId) {
    problems.push(
      `cart identity changed between POST /cart/items (cart_id=${postItemsCartId}) and the ` +
        `follow-up GET /cart (cart_id=${finalCartId}) — this is exactly the SameSite=Lax ` +
        "cross-site symptom Run #62 proved: the guest-cart cookie was not sent, so the API " +
        "minted a brand-new empty cart",
    );
  }
  if (!addedListingPresent) {
    problems.push(
      "the listing added by POST /cart/items is missing from the final GET /cart response",
    );
  }
  return { ok: problems.length === 0, problems, initialCartId, postItemsCartId, finalCartId };
}

/**
 * @param {ReadonlySet<string> | readonly string[]} cookieObservedOnRequests
 * labels actually seen carrying a Cookie header, e.g. "POST /cart/items"
 */
export function evaluateCookieEvidence(cookieObservedOnRequests) {
  const observed = new Set(cookieObservedOnRequests);
  const required = ["POST /cart/items", "GET /cart (final)"];
  const missing = required.filter((label) => !observed.has(label));
  return { ok: missing.length === 0, missing, observed: [...observed] };
}

/**
 * Network-level Cookie-header observer for a Playwright `page.on("request")`
 * stream.
 *
 * MUST use the COMPLETE header API. Playwright's synchronous
 * `request.headers()` does NOT return security-related headers, including
 * Cookie — that is documented Playwright behavior, not a bug to work around:
 * `request.allHeaders()` (async) is the one that includes it. A prior
 * version of this probe read `request.headers()["cookie"]`, which can never
 * be truthy — a false-negative bug that could fail the probe even when
 * SameSite persistence genuinely worked.
 *
 * `req` is duck-typed ({ url(): string, method(): string, allHeaders():
 * Promise<Record<string,string>> }) — no Playwright import here, so this is
 * unit-testable with a plain mock object; see
 * scripts/qa/self-test/customer-stable-cart-probe-lib.test.mjs.
 *
 * `request` events are synchronous and `allHeaders()` is async, so a
 * `page.on("request", handleRequest)` handler that merely calls
 * `allHeaders()` without tracking the returned promise creates a race: the
 * caller could evaluate cookie evidence before the header read resolves.
 * `handleRequest` pushes every in-flight check into an internal list;
 * `waitForPending()` awaits all of them, so a caller that calls it before
 * reading `seen` can never observe that race.
 *
 * Labels the two `GET /cart` calls this probe makes by ORDER (the first
 * `POST /cart/items` flips an internal flag), not just method+path, so the
 * evidence genuinely distinguishes "cookie missing on the very first
 * request, before any cart exists" (expected, not a defect) from "cookie
 * missing on the request AFTER the cart was created" (exactly the Run #62
 * symptom) — a same-labeled generic listener could not tell these apart.
 *
 * @param {{ apiOrigin: string }} args
 */
export function createCookieObserver({ apiOrigin }) {
  /** @type {Set<string>} */
  const seen = new Set();
  /** @type {Promise<void>[]} */
  const pending = [];
  let sawCartItemsPost = false;

  function labelFor(url, method) {
    if (!url.startsWith(apiOrigin)) return null;
    if (method === "POST" && url === `${apiOrigin}/cart/items`) return "POST /cart/items";
    if (method === "GET" && url === `${apiOrigin}/cart`) {
      return sawCartItemsPost ? "GET /cart (final)" : "GET /cart (initial)";
    }
    return null;
  }

  /** @param {{ url(): string, method(): string, allHeaders(): Promise<Record<string,string>> }} req */
  function handleRequest(req) {
    const url = req.url();
    const method = req.method();
    const label = labelFor(url, method);
    if (!label) return;
    if (label === "POST /cart/items") sawCartItemsPost = true;

    const check = Promise.resolve(req.allHeaders())
      .then((headers) => {
        if (headers && headers["cookie"]) {
          seen.add(label);
        }
      })
      .catch(() => {
        // A header-read race with page navigation/context teardown must not
        // crash the probe — an unset label simply fails the cookie-evidence
        // assertion downstream, which is the correct fail-closed outcome.
      });
    pending.push(check);
  }

  async function waitForPending() {
    await Promise.all(pending);
  }

  return { handleRequest, waitForPending, seen };
}

/**
 * Fail-closed check: did navigation actually land on the expected stable
 * hostname, or did Vercel Deployment Protection redirect it away (typically
 * to a vercel.com SSO/login page)? Pure string/URL comparison — no
 * Playwright import, no live target needed to test it.
 *
 * @param {string} landedUrl the URL the browser actually ended up on (e.g.
 *   the main navigation Response's `.url()`, or `page.url()`)
 * @param {string} expectedOrigin
 */
export function detectProtectionChallenge(landedUrl, expectedOrigin) {
  let landed;
  try {
    landed = new URL(landedUrl);
  } catch {
    return { blocked: true, reason: `navigation landed on an unparseable URL: ${landedUrl}` };
  }
  let expected;
  try {
    expected = new URL(expectedOrigin);
  } catch {
    return { blocked: true, reason: `expected origin is not a valid URL: ${expectedOrigin}` };
  }
  if (landed.hostname.toLowerCase() !== expected.hostname.toLowerCase()) {
    return {
      blocked: true,
      reason:
        `navigation landed on ${landed.hostname}, not the stable hostname ${expected.hostname} ` +
        "— this is the signature of a Vercel Deployment Protection / SSO redirect, not the " +
        "Customer app. Confirm VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER is set and valid for " +
        "the convergeo-customer Vercel project.",
    };
  }
  return { blocked: false };
}
