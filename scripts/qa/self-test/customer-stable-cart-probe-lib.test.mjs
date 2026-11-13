import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  assertSameSite,
  buildPdpPath,
  createCookieObserver,
  detectProtectionChallenge,
  evaluateCartIdentity,
  evaluateCookieEvidence,
  parseStableOrigin,
} from "../../../e2e/scripts/customer-stable-cart-probe-lib.mjs";

/** Minimal duck-typed mock of a Playwright Request — no @playwright/test import needed. */
function mockRequest({ url, method, allHeaders }) {
  return {
    url: () => url,
    method: () => method,
    allHeaders: () => allHeaders(),
  };
}

/** A promise that resolves on the next microtask/macrotask tick, to simulate a real async header read. */
function tick(ms = 0) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("customer-stable-cart-probe: parseStableOrigin", () => {
  it("missing value -> SKIPPED-eligible (missing:true)", () => {
    const r = parseStableOrigin("", "CUSTOMER_STAGING_STABLE_URL");
    assert.equal(r.ok, false);
    assert.equal(r.missing, true);
  });

  it("localhost is refused", () => {
    const r = parseStableOrigin("https://localhost:3000", "CUSTOMER_STAGING_STABLE_URL");
    assert.equal(r.ok, false);
    assert.match(r.reason, /localhost/i);
  });

  it("http (non-https) is refused", () => {
    const r = parseStableOrigin(
      "http://customer.staging.vergeo5.com",
      "CUSTOMER_STAGING_STABLE_URL",
    );
    assert.equal(r.ok, false);
    assert.match(r.reason, /https/i);
  });

  it("a *.vercel.app Preview URL is explicitly refused (that's the cross-site case being fixed)", () => {
    const r = parseStableOrigin(
      "https://convergeo-customer-98gijm47m-vergeo-projects.vercel.app",
      "CUSTOMER_STAGING_STABLE_URL",
    );
    assert.equal(r.ok, false);
    assert.match(r.reason, /vercel\.app/i);
  });

  it("a valid stable hostname parses to its origin", () => {
    const r = parseStableOrigin(
      "https://customer.staging.vergeo5.com/en/p/foo",
      "CUSTOMER_STAGING_STABLE_URL",
    );
    assert.equal(r.ok, true);
    assert.equal(r.origin, "https://customer.staging.vergeo5.com");
    assert.equal(r.hostname, "customer.staging.vergeo5.com");
  });

  it("not a URL at all", () => {
    const r = parseStableOrigin("not a url", "CUSTOMER_STAGING_STABLE_URL");
    assert.equal(r.ok, false);
    assert.equal(r.missing, undefined);
  });
});

describe("customer-stable-cart-probe: assertSameSite", () => {
  it("customer.staging.vergeo5.com and api.staging.vergeo5.com are same-site", () => {
    const r = assertSameSite("customer.staging.vergeo5.com", "api.staging.vergeo5.com");
    assert.equal(r.same, true);
    assert.equal(r.customerSite, "vergeo5.com");
    assert.equal(r.apiSite, "vergeo5.com");
  });

  it("a *.vercel.app host and api.staging.vergeo5.com are NOT same-site (Run #62's actual topology)", () => {
    const r = assertSameSite(
      "convergeo-customer-98gijm47m-vergeo-projects.vercel.app",
      "api.staging.vergeo5.com",
    );
    assert.equal(r.same, false);
    assert.equal(r.customerSite, "vercel.app");
    assert.equal(r.apiSite, "vergeo5.com");
  });

  it("is case-insensitive", () => {
    const r = assertSameSite("Customer.Staging.VERGEO5.com", "api.staging.vergeo5.com");
    assert.equal(r.same, true);
  });
});

describe("customer-stable-cart-probe: buildPdpPath", () => {
  it("builds a locale-prefixed PDP path", () => {
    assert.equal(
      buildPdpPath("en", "stg-rv-20260719-product-a"),
      "/en/p/stg-rv-20260719-product-a",
    );
  });
});

describe("customer-stable-cart-probe: evaluateCartIdentity", () => {
  it("PASS: identity persists and the listing is present", () => {
    const r = evaluateCartIdentity({
      initialCartId: "",
      postItemsCartId: "cart-1",
      finalCartId: "cart-1",
      addedListingPresent: true,
    });
    assert.equal(r.ok, true);
    assert.deepEqual(r.problems, []);
  });

  it("FAIL: cart_id changes between POST and the follow-up GET — the Run #62 symptom", () => {
    const r = evaluateCartIdentity({
      initialCartId: "",
      postItemsCartId: "cart-1",
      finalCartId: "cart-2",
      addedListingPresent: true,
    });
    assert.equal(r.ok, false);
    assert.ok(r.problems.some((p) => p.includes("cart identity changed")));
  });

  it("FAIL: POST /cart/items response missing cart_id", () => {
    const r = evaluateCartIdentity({
      initialCartId: "",
      postItemsCartId: "",
      finalCartId: "cart-1",
      addedListingPresent: true,
    });
    assert.equal(r.ok, false);
    assert.ok(r.problems.some((p) => p.includes("POST /cart/items response had no cart_id")));
  });

  it("FAIL: final GET /cart response missing cart_id", () => {
    const r = evaluateCartIdentity({
      initialCartId: "",
      postItemsCartId: "cart-1",
      finalCartId: "",
      addedListingPresent: true,
    });
    assert.equal(r.ok, false);
    assert.ok(r.problems.some((p) => p.includes("final GET /cart response had no cart_id")));
  });

  it("FAIL: added listing missing from the final cart", () => {
    const r = evaluateCartIdentity({
      initialCartId: "",
      postItemsCartId: "cart-1",
      finalCartId: "cart-1",
      addedListingPresent: false,
    });
    assert.equal(r.ok, false);
    assert.ok(r.problems.some((p) => p.includes("missing from the final GET /cart response")));
  });
});

describe("customer-stable-cart-probe: evaluateCookieEvidence", () => {
  it("PASS: Cookie header observed on both required requests", () => {
    const r = evaluateCookieEvidence(new Set(["POST /cart/items", "GET /cart (final)"]));
    assert.equal(r.ok, true);
    assert.deepEqual(r.missing, []);
  });

  it("FAIL: Cookie header missing on the follow-up GET — exactly the RC-6/Run #62 defect", () => {
    const r = evaluateCookieEvidence(new Set(["POST /cart/items"]));
    assert.equal(r.ok, false);
    assert.deepEqual(r.missing, ["GET /cart (final)"]);
  });

  it("FAIL: Cookie header missing on both", () => {
    const r = evaluateCookieEvidence(new Set());
    assert.equal(r.ok, false);
    assert.deepEqual(r.missing, ["POST /cart/items", "GET /cart (final)"]);
  });

  it("accepts a plain array as well as a Set", () => {
    const r = evaluateCookieEvidence(["POST /cart/items", "GET /cart (final)"]);
    assert.equal(r.ok, true);
  });
});

const API_ORIGIN = "https://api.staging.vergeo5.com";

describe("customer-stable-cart-probe: createCookieObserver (Playwright request.headers() bug regression)", () => {
  it("a request whose headers() lacks Cookie but allHeaders() carries it is NOT a false negative", async () => {
    // The exact prior bug: reading `req.headers()["cookie"]` can never see
    // Cookie (Playwright's documented behavior — headers() omits
    // security-related headers). This proves the observer uses allHeaders()
    // instead, by making headers() (if it were called) provably wrong.
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    const req = mockRequest({
      url: `${API_ORIGIN}/cart/items`,
      method: "POST",
      allHeaders: async () => ({
        "content-type": "application/json",
        cookie: "vergeo_guest_cart=abc",
      }),
    });
    // Sanity: this mock's headers() would be the buggy read — assert it's
    // absent/wrong here so a regression that switches back to it is caught.
    assert.equal(req.headers, undefined, "mock intentionally has no synchronous headers()");

    observer.handleRequest(req);
    await observer.waitForPending();

    assert.ok(observer.seen.has("POST /cart/items"));
  });

  it("allHeaders() reporting Cookie is accepted for the final GET /cart", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart/items`,
        method: "POST",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart`,
        method: "GET",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    await observer.waitForPending();

    assert.ok(observer.seen.has("POST /cart/items"));
    assert.ok(observer.seen.has("GET /cart (final)"));
  });

  it("no Cookie in the complete headers correctly fails (the real Run #62 signature)", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart/items`,
        method: "POST",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart`,
        method: "GET",
        allHeaders: async () => ({ "content-type": "application/json" }), // no cookie
      }),
    );
    await observer.waitForPending();

    assert.ok(observer.seen.has("POST /cart/items"));
    assert.equal(observer.seen.has("GET /cart (final)"), false);
  });

  it("async header inspection completes before the caller evaluates evidence (race closed)", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    let resolveHeaders;
    const slowHeaders = new Promise((resolve) => {
      resolveHeaders = () => resolve({ cookie: "vergeo_guest_cart=abc" });
    });
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart/items`,
        method: "POST",
        allHeaders: () => slowHeaders,
      }),
    );

    // Immediately after handleRequest returns, the async header read has not
    // resolved yet — this is the exact race the fix must close.
    assert.equal(observer.seen.has("POST /cart/items"), false);

    resolveHeaders();
    await observer.waitForPending();

    assert.ok(
      observer.seen.has("POST /cart/items"),
      "waitForPending() must await the in-flight read",
    );
  });

  it("distinguishes the initial GET /cart (before any cart exists) from the final GET /cart (after POST)", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    // Initial GET: legitimately no cookie yet — must not be mislabeled "final".
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart`,
        method: "GET",
        allHeaders: async () => ({}),
      }),
    );
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart/items`,
        method: "POST",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart`,
        method: "GET",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    await observer.waitForPending();

    assert.equal(observer.seen.has("GET /cart (initial)"), false);
    assert.ok(observer.seen.has("GET /cart (final)"));
  });

  it("ignores requests to unrelated origins (e.g. the stable Customer hostname itself)", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    observer.handleRequest(
      mockRequest({
        url: "https://customer.staging.vergeo5.com/en/p/foo",
        method: "GET",
        allHeaders: async () => ({ cookie: "vergeo_guest_cart=abc" }),
      }),
    );
    await observer.waitForPending();
    assert.equal(observer.seen.size, 0);
  });

  it("a rejected allHeaders() promise fails closed (not observed) rather than crashing the probe", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart/items`,
        method: "POST",
        allHeaders: async () => {
          throw new Error("context torn down mid-navigation");
        },
      }),
    );
    await assert.doesNotReject(observer.waitForPending());
    assert.equal(observer.seen.has("POST /cart/items"), false);
  });

  it("HttpOnly does not require document.cookie access — this module runs in plain Node, which has no `document` global at all", () => {
    assert.equal(typeof globalThis.document, "undefined");
  });

  it("real async timing (setTimeout) still resolves correctly, not just a synchronously-resolved mock", async () => {
    const observer = createCookieObserver({ apiOrigin: API_ORIGIN });
    observer.handleRequest(
      mockRequest({
        url: `${API_ORIGIN}/cart`,
        method: "GET",
        allHeaders: async () => {
          await tick(5);
          return { cookie: "vergeo_guest_cart=abc" };
        },
      }),
    );
    await observer.waitForPending();
    assert.ok(observer.seen.has("GET /cart (initial)"));
  });
});

describe("customer-stable-cart-probe: detectProtectionChallenge", () => {
  it("landing on the expected hostname is not blocked", () => {
    const r = detectProtectionChallenge(
      "https://customer.staging.vergeo5.com/en/p/foo",
      "https://customer.staging.vergeo5.com",
    );
    assert.equal(r.blocked, false);
  });

  it("landing on a different host (e.g. Vercel SSO) is blocked", () => {
    const r = detectProtectionChallenge(
      "https://vercel.com/sso-api/foo?bar=baz",
      "https://customer.staging.vergeo5.com",
    );
    assert.equal(r.blocked, true);
    assert.match(r.reason, /vercel\.com/);
  });

  it("an unparseable landed URL is blocked (fails closed)", () => {
    const r = detectProtectionChallenge("not a url", "https://customer.staging.vergeo5.com");
    assert.equal(r.blocked, true);
  });

  it("hostname comparison is case-insensitive", () => {
    const r = detectProtectionChallenge(
      "https://Customer.Staging.VERGEO5.com/en",
      "https://customer.staging.vergeo5.com",
    );
    assert.equal(r.blocked, false);
  });
});
