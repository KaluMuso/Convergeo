import { afterEach, describe, expect, it } from "vitest";

import { isGoogleAuthEnabled } from "./google-auth";

describe("isGoogleAuthEnabled", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED;
  });

  it("defaults to off when configuration is absent", () => {
    expect(isGoogleAuthEnabled({})).toBe(false);
    expect(isGoogleAuthEnabled()).toBe(false);
  });

  it("defaults to off for any value other than the exact string true", () => {
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "" })).toBe(false);
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "false" })).toBe(false);
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "TRUE" })).toBe(false);
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "1" })).toBe(false);
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "yes" })).toBe(false);
  });

  it("enables only for the exact string true", () => {
    expect(isGoogleAuthEnabled({ NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: "true" })).toBe(true);
    process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED = "true";
    expect(isGoogleAuthEnabled()).toBe(true);
  });
});
