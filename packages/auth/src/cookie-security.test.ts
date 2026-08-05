import { describe, expect, it } from "vitest";

import { mergeSecureCookieOptions, secureCookieDefaults } from "./cookie-security";

describe("secureCookieDefaults", () => {
  it("requires Secure in production", () => {
    expect(secureCookieDefaults({ NODE_ENV: "production" })).toEqual({
      httpOnly: true,
      secure: true,
      sameSite: "lax",
    });
  });

  it("allows non-secure cookies in development", () => {
    expect(secureCookieDefaults({ NODE_ENV: "development" })).toEqual({
      httpOnly: true,
      secure: false,
      sameSite: "lax",
    });
  });
});

describe("mergeSecureCookieOptions", () => {
  it("preserves explicit Supabase overrides", () => {
    expect(
      mergeSecureCookieOptions(
        { path: "/", maxAge: 3600, secure: false },
        { NODE_ENV: "production" },
      ),
    ).toEqual({
      path: "/",
      maxAge: 3600,
      httpOnly: true,
      secure: false,
      sameSite: "lax",
    });
  });
});
