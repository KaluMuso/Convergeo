import { describe, expect, it } from "vitest";

import {
  adminPermissionDeniedPath,
  defaultPortalHomePath,
  sanitizeNextPath,
  vendorOnboardingPath,
} from "./safe-next";

describe("sanitizeNextPath", () => {
  const fallback = "/en";

  it("accepts locale-prefixed application paths", () => {
    expect(sanitizeNextPath("en", "/en", fallback)).toBe("/en");
    expect(sanitizeNextPath("en", "/en/listings", fallback)).toBe("/en/listings");
    expect(sanitizeNextPath("bem", "/bem/onboarding/status", "/bem")).toBe(
      "/bem/onboarding/status",
    );
    expect(sanitizeNextPath("en", "/en/account?tab=orders", fallback)).toBe(
      "/en/account?tab=orders",
    );
  });

  it("rejects absolute and protocol-relative URLs", () => {
    expect(sanitizeNextPath("en", "https://evil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "http://evil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "//evil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "/\\evil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "\\\\evil.example", fallback)).toBe(fallback);
  });

  it("rejects javascript and other schemes", () => {
    expect(sanitizeNextPath("en", "javascript:alert(1)", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "/javascript:alert(1)", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "data:text/html,hi", fallback)).toBe(fallback);
  });

  it("rejects malformed encoded external URLs", () => {
    expect(sanitizeNextPath("en", "%2F%2Fevil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "%2f%2fevil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "%5C%5Cevil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", encodeURIComponent("https://evil.example"), fallback)).toBe(
      fallback,
    );
    expect(
      sanitizeNextPath("en", encodeURIComponent(encodeURIComponent("//evil.example")), fallback),
    ).toBe(fallback);
  });

  it("rejects cross-locale and prefix-confused paths", () => {
    expect(sanitizeNextPath("en", "/fr/account", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "/english", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "/en.evil.example", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "/en%2f%2fevil.example", fallback)).toBe(fallback);
  });

  it("rejects path traversal and empty/malformed values", () => {
    expect(sanitizeNextPath("en", "/en/../admin", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", null, fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "   ", fallback)).toBe(fallback);
    expect(sanitizeNextPath("en", "%E0%A4%A", fallback)).toBe(fallback);
  });
});

describe("portal default paths", () => {
  it("keeps localized home, onboarding, and permission-denied routes", () => {
    expect(defaultPortalHomePath("fr")).toBe("/fr");
    expect(vendorOnboardingPath("nya")).toBe("/nya/onboarding");
    expect(adminPermissionDeniedPath("zh")).toBe("/zh/permission-denied");
  });
});
