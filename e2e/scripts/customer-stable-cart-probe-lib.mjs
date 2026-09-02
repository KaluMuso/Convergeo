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
