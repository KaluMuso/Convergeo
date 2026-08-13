import { describe, expect, it } from "vitest";

import { AUTH_PORTALS, isAuthPortal } from "./portal";

describe("AuthPortal", () => {
  it("enumerates customer, vendor, and admin", () => {
    expect(AUTH_PORTALS).toEqual(["customer", "vendor", "admin"]);
  });

  it("rejects unknown portals", () => {
    expect(isAuthPortal("customer")).toBe(true);
    expect(isAuthPortal("staff")).toBe(false);
    expect(isAuthPortal(null)).toBe(false);
  });
});
