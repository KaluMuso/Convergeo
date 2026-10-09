import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CSP_NONCE_HEADER,
  CSP_NONCE_PLACEHOLDER,
  CSP_REPORT_ONLY_HEADER,
  CSP_REPORTING_ENDPOINTS_HEADER,
  appendCspReporting,
  applyReportOnlyCspNonce,
  createLoginRedirect,
  createPortalRedirect,
  getLocaleFromPath,
  handleCspReportRequest,
  isAdminBypassActive,
  isAdminPermissionDeniedPath,
  isAuthExemptPath,
  isCspReportRequest,
  isHealthCheckPath,
  isVendorOnboardingPath,
  mergeSessionCookies,
  resolveGatedRedirect,
  shouldRedirectToLogin,
  updateSession,
} from "./middleware";

const getUser = vi.fn();
const getClaims = vi.fn();

function verifiedClaims(roles: unknown, overrides: Record<string, unknown> = {}) {
  return {
    data: {
      claims: {
        sub: "user-1",
        iss: "https://example.supabase.co/auth/v1",
        aud: "authenticated",
        exp: Math.floor(Date.now() / 1000) + 3600,
        app_metadata: { roles },
        ...overrides,
      },
    },
    error: null,
  };
}

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn(() => ({
    auth: {
      getUser,
      getClaims,
    },
  })),
}));

describe("updateSession", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
    getUser.mockReset();
    getClaims.mockReset();
    getClaims.mockResolvedValue({ data: null, error: null });
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
    expect(getClaims).not.toHaveBeenCalled();
  });

  it("reads verified claim roles when the User object has none", async () => {
    getUser.mockResolvedValue({
      data: {
        user: {
          id: "user-1",
          app_metadata: {},
        },
      },
    });
    getClaims.mockResolvedValue(verifiedClaims(["customer", "vendor", "admin"]));

    const request = new NextRequest("http://localhost:3001/en");
    const result = await updateSession(request);

    expect(result.user?.id).toBe("user-1");
    expect(result.roles).toEqual(["customer", "vendor", "admin"]);
    expect(getClaims).toHaveBeenCalledOnce();
    expect(
      resolveGatedRedirect("vendor", "/en/listings", ["en"], result.user, result.roles),
    ).toBeNull();
    expect(resolveGatedRedirect("admin", "/en", ["en"], result.user, result.roles)).toBeNull();
  });

  it.each([
    ["customer", "onboarding", "permission-denied"],
    ["vendor", null, "permission-denied"],
    ["admin", "onboarding", null],
  ] as const)("preserves %s routing gates", async (role, vendorRedirect, adminRedirect) => {
    getUser.mockResolvedValue({ data: { user: { id: "user-1", app_metadata: {} } } });
    getClaims.mockResolvedValue(verifiedClaims([role]));
    const result = await updateSession(new NextRequest("http://localhost:3001/en"));
    expect(resolveGatedRedirect("vendor", "/en/listings", ["en"], result.user, result.roles)).toBe(
      vendorRedirect,
    );
    expect(resolveGatedRedirect("admin", "/en", ["en"], result.user, result.roles)).toBe(
      adminRedirect,
    );
  });

  it.each([
    ["wrong issuer", { iss: "https://other.supabase.co/auth/v1" }],
    ["wrong audience", { aud: "anon" }],
    ["missing audience", { aud: undefined }],
    ["expired", { exp: Math.floor(Date.now() / 1000) - 1 }],
    ["missing expiration", { exp: undefined }],
    ["wrong subject", { sub: "other-user" }],
    ["malformed roles", { app_metadata: { roles: "vendor" } }],
    ["user metadata spoof", { app_metadata: {}, user_metadata: { roles: ["vendor"] } }],
  ])("fails closed for %s", async (_case, overrides) => {
    getUser.mockResolvedValue({
      data: { user: { id: "user-1", app_metadata: { roles: ["vendor"] } } },
    });
    getClaims.mockResolvedValue(verifiedClaims(["vendor"], overrides));
    const result = await updateSession(new NextRequest("http://localhost:3001/en"));
    expect(result.roles).toEqual([]);
    expect(resolveGatedRedirect("vendor", "/en/listings", ["en"], result.user, result.roles)).toBe(
      "onboarding",
    );
  });

  it("fails closed when claim verification returns no claims or an error", async () => {
    getUser.mockResolvedValue({ data: { user: { id: "user-1", app_metadata: {} } } });
    for (const response of [
      { data: null, error: null },
      { data: null, error: { message: "verification failed" } },
    ]) {
      getClaims.mockResolvedValueOnce(response);
      const result = await updateSession(new NextRequest("http://localhost:3001/en"));
      expect(result.roles).toEqual([]);
    }
    getClaims.mockRejectedValueOnce(new Error("JWKS unavailable"));
    const result = await updateSession(new NextRequest("http://localhost:3001/en"));
    expect(result.roles).toEqual([]);
  });

  // Scenario G: user_metadata must never be trusted as a role source, even
  // if it happens to carry a "roles"-shaped payload.
  it("G — user_metadata on the claims is never trusted for roles", async () => {
    getUser.mockResolvedValue({ data: { user: { id: "user-1", app_metadata: {} } } });
    getClaims.mockResolvedValue({
      data: {
        claims: {
          app_metadata: {},
          user_metadata: { roles: ["vendor"] },
        },
      },
      error: null,
    });

    const request = new NextRequest("http://localhost:3001/en");
    const result = await updateSession(request);

    expect(result.roles).toEqual([]);
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

describe("applyReportOnlyCspNonce", () => {
  it("substitutes the report-only CSP nonce and forwards it on the request", () => {
    const request = new NextRequest("http://localhost:3000/en");
    const response = applyReportOnlyCspNonce(
      request,
      NextResponse.next(),
      `script-src 'self' 'strict-dynamic' 'nonce-${CSP_NONCE_PLACEHOLDER}'`,
      "fixed-test-nonce",
    );

    expect(response.headers.get(CSP_REPORT_ONLY_HEADER)).toBe(
      "script-src 'self' 'strict-dynamic' 'nonce-fixed-test-nonce'; report-uri /api/csp-report; report-to csp-endpoint",
    );
    expect(response.headers.get(CSP_REPORTING_ENDPOINTS_HEADER)).toBe(
      'csp-endpoint="/api/csp-report"',
    );
    expect(response.headers.get(`x-middleware-request-${CSP_NONCE_HEADER}`)).toBe(
      "fixed-test-nonce",
    );
    expect(
      response.headers.get(`x-middleware-request-${CSP_REPORT_ONLY_HEADER.toLowerCase()}`),
    ).toBe(
      "script-src 'self' 'strict-dynamic' 'nonce-fixed-test-nonce'; report-uri /api/csp-report; report-to csp-endpoint",
    );
  });
});

describe("CSP reporting helpers", () => {
  it("detects and accepts CSP report POSTs", async () => {
    const request = new NextRequest("http://localhost:3000/api/csp-report", {
      method: "POST",
      headers: { "content-type": "application/csp-report" },
      body: JSON.stringify({
        "csp-report": {
          "blocked-uri": "https://evil.example",
          "violated-directive": "script-src",
        },
      }),
    });

    expect(isCspReportRequest(request)).toBe(true);
    const response = await handleCspReportRequest(request);
    expect(response.status).toBe(204);
  });

  it("appends report directives once", () => {
    const policy = appendCspReporting("default-src 'self'");
    expect(policy).toContain("report-uri /api/csp-report");
    expect(policy).toContain("report-to csp-endpoint");
    expect(appendCspReporting(policy)).toBe(policy);
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

  it("otp routes stay exempt for gated apps — mid-login has no session yet", () => {
    // A phone-OTP login is two anonymous requests (send code, then verify it);
    // gating /otp like any other route would bounce a mid-login vendor back to
    // /login before they can ever submit the code. `request.nextUrl.pathname`
    // never carries the query string, so `?phone=...` is not part of this input.
    expect(shouldRedirectToLogin("vendor", "/en/otp", locales, null, [])).toBe(false);
    expect(isAuthExemptPath("/en/otp", locales)).toBe(true);
    expect(isAuthExemptPath("/nya/otp", locales)).toBe(true);
    // Confirms this is a segment match, not a substring match.
    expect(isAuthExemptPath("/en/otpish", locales)).toBe(false);
  });

  it("authenticated customers can reach vendor onboarding without vendor role", () => {
    expect(isVendorOnboardingPath("/en/onboarding", locales)).toBe(true);
    expect(isVendorOnboardingPath("/fr/onboarding/status", locales)).toBe(true);
    expect(isVendorOnboardingPath("/en/listings", locales)).toBe(false);

    expect(
      shouldRedirectToLogin("vendor", "/en/onboarding", locales, { id: "user-1" } as never, [
        "customer",
      ]),
    ).toBe(false);
    expect(
      shouldRedirectToLogin(
        "vendor",
        "/en/onboarding/status",
        locales,
        { id: "user-1" } as never,
        [],
      ),
    ).toBe(false);
    expect(
      shouldRedirectToLogin("vendor", "/en/listings", locales, { id: "user-1" } as never, [
        "customer",
      ]),
    ).toBe(true);
    expect(shouldRedirectToLogin("vendor", "/en/onboarding", locales, null, [])).toBe(true);
  });

  it("sends authenticated non-vendors to onboarding rather than login", () => {
    expect(
      resolveGatedRedirect("vendor", "/en/listings", locales, { id: "user-1" } as never, [
        "customer",
      ]),
    ).toBe("onboarding");
    expect(resolveGatedRedirect("vendor", "/en/listings", locales, null, [])).toBe("login");
    expect(
      resolveGatedRedirect("vendor", "/en", locales, { id: "user-1" } as never, ["vendor"]),
    ).toBeNull();
  });

  it("matches only the exact /{locale}/health path", () => {
    expect(isHealthCheckPath("/en/health", locales)).toBe(true);
    expect(isHealthCheckPath("/bem/health", locales)).toBe(true);
    expect(isHealthCheckPath("/nya/health", locales)).toBe(true);
    expect(isHealthCheckPath("/en/health/", locales)).toBe(true);
    expect(isHealthCheckPath("/en/health/extra", locales)).toBe(false);
    expect(isHealthCheckPath("/en/healthcheck", locales)).toBe(false);
    expect(isHealthCheckPath("/health", locales)).toBe(false);
    expect(isHealthCheckPath("/xx/health", locales)).toBe(false);
    expect(isHealthCheckPath("/", locales)).toBe(false);
  });

  it("does not treat authentication as admin authorization", () => {
    expect(isAdminPermissionDeniedPath("/en/permission-denied", locales)).toBe(true);
    expect(
      resolveGatedRedirect("admin", "/en", locales, { id: "user-1" } as never, ["customer"]),
    ).toBe("permission-denied");
    expect(
      resolveGatedRedirect("admin", "/en/permission-denied", locales, { id: "user-1" } as never, [
        "customer",
      ]),
    ).toBeNull();
    expect(resolveGatedRedirect("admin", "/en", locales, null, [])).toBe("login");
    expect(
      resolveGatedRedirect("admin", "/en", locales, { id: "user-1" } as never, ["admin"]),
    ).toBeNull();
  });

  it("builds portal redirects without weakening the login next parameter", () => {
    const request = new NextRequest("http://localhost:3001/en/listings");
    const onboarding = createPortalRedirect("onboarding", request, "en", NextResponse.next());
    const denied = createPortalRedirect("permission-denied", request, "en", NextResponse.next());

    expect(onboarding.headers.get("location")).toBe("http://localhost:3001/en/onboarding");
    expect(denied.headers.get("location")).toBe("http://localhost:3001/en/permission-denied");
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
