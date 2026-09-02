import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  assertSameSite,
  buildPdpPath,
  evaluateCartIdentity,
  evaluateCookieEvidence,
  parseStableOrigin,
} from "../../../e2e/scripts/customer-stable-cart-probe-lib.mjs";

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
