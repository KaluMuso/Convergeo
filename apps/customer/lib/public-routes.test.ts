import { describe, expect, it } from "vitest";

import { isPublicCustomerRoute } from "./public-routes";

describe("isPublicCustomerRoute", () => {
  it.each([
    "/en",
    "/en/p/itel-a70",
    "/bem/search",
    "/fr/c/phones/all",
    "/nya/e/x",
    "/en/legal/terms",
  ])("treats %s as public", (path) => expect(isPublicCustomerRoute(path)).toBe(true));
  it.each([
    "/en/account",
    "/en/account/orders/1",
    "/en/checkout",
    "/en/checkout/card/pay-1",
    "/en/cart",
    "/en/wishlist",
    "/en/ask",
    "/en/login",
    "/en/otp",
    "/api/contact",
    "/",
    "/cart",
    "/xx/p/a",
  ])("keeps the server check for %s", (path) => expect(isPublicCustomerRoute(path)).toBe(false));

  it("never treats mutating methods as public", () => {
    expect(isPublicCustomerRoute("/en/p/a", "POST")).toBe(false);
    expect(isPublicCustomerRoute("/en/p/a", "HEAD")).toBe(true);
  });
});
