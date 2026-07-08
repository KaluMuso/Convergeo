import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createLoginRedirect,
  getLocaleFromPath,
  isAdminBypassActive,
  isAuthExemptPath,
  mergeSessionCookies,
  shouldRedirectToLogin,
  updateSession,
} from "./middleware";

const getUser = vi.fn();

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn(() => ({
    auth: {
      getUser,
    },
  })),
}));

describe("updateSession", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
    getUser.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns refreshed session cookies on the response", async () => {
    getUser.mockResolvedValue({ data: { user: null } });

    const request = new NextRequest("http://localhost:3000/en");
    const result = await updateSession(request);

    expect(result.response).toBeInstanceOf(NextResponse);
    expect(result.user).toBeNull();
    expect(result.roles).toEqual([]);
    expect(getUser).toHaveBeenCalledOnce();
  });

  it("extracts roles from the authenticated user", async () => {
    getUser.mockResolvedValue({
      data: {
        user: {
          id: "user-1",
          app_metadata: { roles: ["vendor"] },
        },
      },
    });

    const request = new NextRequest("http://localhost:3001/en");
    const result = await updateSession(request);

    expect(result.user?.id).toBe("user-1");
    expect(result.roles).toEqual(["vendor"]);
  });
});

describe("mergeSessionCookies", () => {
  it("copies cookies from the auth response onto the locale response", () => {
    const source = NextResponse.next();
    source.cookies.set("sb-access-token", "token", { httpOnly: true });

    const target = NextResponse.next();
    mergeSessionCookies(source, target);

    expect(target.cookies.get("sb-access-token")?.value).toBe("token");
  });
});

describe("middleware matrix", () => {
  const locales = ["en", "bem", "nya", "fr"] as const;

  it("customer logged-out passes through without login redirect", () => {
    expect(shouldRedirectToLogin("none", "/en/products", locales, null, [])).toBe(false);
  });

  it("vendor without session redirects to login", () => {
    expect(shouldRedirectToLogin("vendor", "/en/dashboard", locales, null, [])).toBe(true);
  });

  it("vendor with vendor role passes", () => {
    expect(
      shouldRedirectToLogin("vendor", "/en/dashboard", locales, { id: "user-1" } as never, [
        "vendor",
      ]),
    ).toBe(false);
  });

  it("admin non-admin redirects", () => {
    expect(
      shouldRedirectToLogin("admin", "/en", locales, { id: "user-1" } as never, ["vendor"]),
    ).toBe(true);
  });

  it("admin with admin role passes", () => {
    expect(
      shouldRedirectToLogin("admin", "/en", locales, { id: "user-1" } as never, ["admin"]),
    ).toBe(false);
  });

  it("login routes stay exempt for gated apps", () => {
    expect(shouldRedirectToLogin("vendor", "/en/login", locales, null, [])).toBe(false);
    expect(shouldRedirectToLogin("admin", "/fr/login", locales, null, [])).toBe(false);
  });

  it("locale routing helpers preserve locale on redirects", () => {
    expect(getLocaleFromPath("/", locales, "en")).toBe("en");
    expect(getLocaleFromPath("/bem/dashboard", locales, "en")).toBe("bem");
    expect(isAuthExemptPath("/nya/login", locales)).toBe(true);

    const request = new NextRequest("http://localhost:3001/bem/dashboard");
    const redirect = createLoginRedirect(request, "bem", NextResponse.next());

    expect(redirect.headers.get("location")).toBe(
      "http://localhost:3001/bem/login?next=%2Fbem%2Fdashboard",
    );
  });

  it("admin bypass is off by default and only active in non-production", () => {
    const originalNodeEnv = process.env.NODE_ENV;
    const originalBypass = process.env.NEXT_PUBLIC_ADMIN_BYPASS;

    process.env.NODE_ENV = "development";
    delete process.env.NEXT_PUBLIC_ADMIN_BYPASS;
    expect(isAdminBypassActive()).toBe(false);

    process.env.NEXT_PUBLIC_ADMIN_BYPASS = "true";
    expect(isAdminBypassActive()).toBe(true);

    process.env.NODE_ENV = "production";
    expect(isAdminBypassActive()).toBe(false);

    process.env.NODE_ENV = originalNodeEnv;
    process.env.NEXT_PUBLIC_ADMIN_BYPASS = originalBypass;
  });

  it("admin bypass skips login redirect in non-production", () => {
    expect(shouldRedirectToLogin("admin", "/en", locales, null, [], { adminBypass: true })).toBe(
      false,
    );
  });
});
