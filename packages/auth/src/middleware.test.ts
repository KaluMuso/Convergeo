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
