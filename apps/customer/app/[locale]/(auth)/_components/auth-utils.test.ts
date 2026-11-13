import { describe, expect, it } from "vitest";

import authMessages from "../../../../../../packages/i18n/messages/en/auth.json";

import {
  formatE164,
  forwardableNextParam,
  isOnboardingComplete,
  isValidZambianMobile,
  maskPhone,
  normalizeNationalNumber,
  parseAuthError,
  parseRetryAfterFromResponse,
  resolveCustomerPostAuthPath,
  resolvePostAuthPath,
} from "./auth-utils";

function collectLeafKeys(node: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      keys.push(path);
    } else if (value && typeof value === "object") {
      keys.push(...collectLeafKeys(value as Record<string, unknown>, path));
    }
  }
  return keys;
}

const REQUIRED_AUTH_KEYS = [
  "login.title",
  "login.submit",
  "signup.title",
  "signup.submit",
  "otp.title",
  "otp.sent",
  "otp.resend",
  "otp.resendIn",
  "errors.wrongCode",
  "errors.expired",
  "errors.throttled",
  "errors.invalidPhone",
  "email.submitLogin",
  "google.loading",
] as const;

describe("auth-utils", () => {
  it("normalizes Zambian national numbers", () => {
    expect(normalizeNationalNumber("97 123 4567")).toBe("971234567");
    expect(formatE164("+260", "971234567")).toBe("+260971234567");
  });

  it("validates Zambian mobile prefixes", () => {
    expect(isValidZambianMobile("971234567")).toBe(true);
    expect(isValidZambianMobile("771234567")).toBe(true);
    expect(isValidZambianMobile("871234567")).toBe(false);
  });

  it("masks phone numbers for display", () => {
    expect(maskPhone("+260971234567")).toContain("567");
  });

  it("maps auth errors to UI codes", () => {
    expect(parseAuthError({ message: "Token has expired" }).code).toBe("expired");
    expect(parseAuthError({ message: "Invalid OTP" }).code).toBe("wrong_code");
    expect(parseAuthError({ status: 429, retryAfter: 45 }).code).toBe("throttled");
  });

  it("reads retry-after from 429 responses", () => {
    const response = new Response(null, {
      status: 429,
      headers: { "retry-after": "30" },
    });
    expect(parseRetryAfterFromResponse(response)).toBe(30);
  });

  it("resolves safe post-auth paths", () => {
    expect(resolvePostAuthPath("en", "/en/account", "/en")).toBe("/en/account");
    expect(resolvePostAuthPath("en", "https://evil.test", "/en")).toBe("/en");
    expect(resolvePostAuthPath("en", "/fr/account", "/en")).toBe("/en");
    expect(resolvePostAuthPath("en", "//evil.example", "/en")).toBe("/en");
    expect(resolvePostAuthPath("en", "javascript:alert(1)", "/en")).toBe("/en");
    expect(resolvePostAuthPath("en", "%2F%2Fevil.example", "/en")).toBe("/en");
    expect(resolvePostAuthPath("en", "/english", "/en")).toBe("/en");
  });

  it("routes incomplete onboarding to welcome", () => {
    expect(resolveCustomerPostAuthPath("en", null, "/en", false)).toBe("/en/welcome");
    expect(resolveCustomerPostAuthPath("en", "/en/account", "/en", false)).toBe(
      "/en/welcome?next=%2Fen%2Faccount",
    );
    expect(resolveCustomerPostAuthPath("en", null, "/en", true)).toBe("/en");
  });

  it("detects onboarding completion from completed_at", () => {
    expect(isOnboardingComplete(null)).toBe(false);
    expect(isOnboardingComplete({ completed_at: null })).toBe(false);
    expect(isOnboardingComplete({ completed_at: "2026-07-23T12:00:00Z" })).toBe(true);
  });
});

describe("forwardableNextParam", () => {
  it("carries a safe same-origin, locale-prefixed destination forward", () => {
    expect(forwardableNextParam("en", "/en/services")).toBe("/en/services");
    expect(forwardableNextParam("en", "/en/events/synthetic-event/scan")).toBe(
      "/en/events/synthetic-event/scan",
    );
    expect(forwardableNextParam("en", "/en")).toBe("/en");
  });

  it("returns null when there is nothing to carry (default behavior unchanged)", () => {
    expect(forwardableNextParam("en", undefined)).toBeNull();
    expect(forwardableNextParam("en", null)).toBeNull();
    expect(forwardableNextParam("en", "")).toBeNull();
  });

  it("drops every open-redirect shape resolvePostAuthPath already rejects", () => {
    // Same corpus as the resolvePostAuthPath case above: an attacker-controlled
    // absolute URL must not even be echoed into the intermediate OTP URL, let
    // alone become a post-auth redirect.
    for (const hostile of [
      "https://evil.test",
      "//evil.example",
      "javascript:alert(1)",
      "%2F%2Fevil.example",
      "/en/../../evil",
      "/en\\evil.example",
      "/fr/account",
      "/english",
      "not-a-path",
    ]) {
      expect(forwardableNextParam("en", hostile)).toBeNull();
    }
  });

  it("never returns the internal rejection sentinel as a destination", () => {
    expect(forwardableNextParam("en", "__vergeo_rejected_next__")).toBeNull();
  });
});

describe("auth i18n", () => {
  it("uses nested keys without flat dotted top-level entries", () => {
    for (const key of Object.keys(authMessages)) {
      expect(key.includes(".")).toBe(false);
    }

    const leaves = collectLeafKeys(authMessages as Record<string, unknown>);
    expect(leaves.length).toBeGreaterThan(20);

    for (const required of REQUIRED_AUTH_KEYS) {
      expect(leaves).toContain(required);
    }
  });
});
