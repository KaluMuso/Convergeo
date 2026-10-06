import {
  CSP_NONCE_PLACEHOLDER,
  CSP_REPORT_ONLY_HEADER,
  updateSession,
} from "@vergeo/auth/middleware";
import { LOCALES } from "@vergeo/i18n";
import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

const { resolveGatedRedirectMock } = vi.hoisted(() => ({
  resolveGatedRedirectMock: vi.fn(),
}));

vi.mock("@vergeo/auth/middleware", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/auth/middleware")>();
  return {
    ...actual,
    createPortalRedirect: vi.fn(
      (
        kind: "login" | "onboarding" | "permission-denied",
        request: NextRequest,
        locale: string,
        sessionResponse: NextResponse,
      ) => {
        const path = kind === "login" ? `/${locale}/login` : `/${locale}/${kind}`;
        const redirect = NextResponse.redirect(new URL(path, request.url));
        return actual.mergeSessionCookies(sessionResponse, redirect);
      },
    ),
    getLocaleFromPath: vi.fn(() => "en"),
    resolveGatedRedirect: resolveGatedRedirectMock,
    updateSession: vi.fn(async () => ({
      response: NextResponse.next(),
      user: null,
      roles: [],
    })),
  };
});

import { isVendorPasswordRecoveryPath } from "./lib/password-recovery-path";
import middleware, { config } from "./middleware";

describe("vendor middleware matcher", () => {
  it("keeps the CSP report path and the broadened locale-redirect matcher", () => {
    expect(config.matcher).toEqual(["/api/csp-report", "/((?!api|_next|_vercel|.*\\..*).*)"]);
  });

  it("matches locale-less app paths so the gate check and next-intl redirect both run on them (regression: a bare path like `/onboarding` used to skip both, land on `/[locale]` with an invalid locale value, and throw formatting any interpolated message)", () => {
    const pattern = new RegExp(`^${config.matcher[1]}$`);
    expect(pattern.test("/onboarding")).toBe(true);
    expect(pattern.test("/listings")).toBe(true);
    expect(pattern.test("/en/listings")).toBe(true);
  });

  it("still excludes Next internals, other API routes, and static files with an extension", () => {
    const pattern = new RegExp(`^${config.matcher[1]}$`);
    expect(pattern.test("/api/csp-report")).toBe(false);
    expect(pattern.test("/_next/static/chunk.js")).toBe(false);
    expect(pattern.test("/favicon.ico")).toBe(false);
  });
});

describe("vendor password recovery gate", () => {
  beforeEach(async () => {
    const actual =
      await vi.importActual<typeof import("@vergeo/auth/middleware")>("@vergeo/auth/middleware");
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockImplementation(actual.resolveGatedRedirect);
    vi.mocked(updateSession).mockResolvedValue({
      response: NextResponse.next(),
      user: null,
      roles: [],
    });
  });

  it.each(
    LOCALES.flatMap((locale) => [
      `/${locale}/reset-password`,
      `/${locale}/reset-password/confirm`,
      `/${locale}/reset-password/`,
      `/${locale}/reset-password/confirm/`,
    ]),
  )("allows exact recovery without a session: %s", async (path) => {
    const response = await middleware(
      new NextRequest(`https://vendor.example.test${path}?next=https://evil.example.test`),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
    expectNonceReportOnlyCsp(response);
  });

  it.each([
    "/en/listings",
    "/en/orders",
    "/en/reset-password/admin",
    "/en/reset-password/confirm/admin",
    "/en/reset-password-other",
  ])("keeps unauthenticated non-recovery paths gated: %s", async (path) => {
    const response = await middleware(new NextRequest(`https://vendor.example.test${path}`));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://vendor.example.test/en/login");
    expect(resolveGatedRedirectMock).toHaveBeenCalledOnce();
  });

  it.each([
    "/xx/reset-password",
    "/reset-password",
    "/en/reset-password//",
    "/en/reset-password/confirm-extra",
  ])("rejects lookalike/unsupported recovery paths: %s", (path) =>
    expect(isVendorPasswordRecoveryPath(path)).toBe(false),
  );

  it.each(["customer", "vendor"] as const)(
    "preserves the real shared role gate for %s",
    async (role) => {
      vi.mocked(updateSession).mockResolvedValue({
        response: NextResponse.next(),
        user: {
          id: "synthetic",
          app_metadata: {},
          user_metadata: {},
          aud: "authenticated",
          created_at: "2026-01-01",
        },
        roles: [role],
      });
      for (const path of [
        "/en/listings",
        "/en/services",
        "/en/orders",
        "/en/events/synthetic/scan",
      ]) {
        const response = await middleware(new NextRequest(`https://vendor.example.test${path}`));
        expect(response.status, path).toBe(role === "vendor" ? 200 : 307);
        expect(response.headers.get("location"), path).toBe(
          role === "vendor" ? null : "https://vendor.example.test/en/onboarding",
        );
        expectNonceReportOnlyCsp(response);
      }
    },
  );

  it("preserves refreshed session cookies on recovery responses", async () => {
    const sessionResponse = NextResponse.next();
    sessionResponse.cookies.set("synthetic-refresh", "fixture", { httpOnly: true });
    vi.mocked(updateSession).mockResolvedValue({
      response: sessionResponse,
      user: null,
      roles: [],
    });
    const response = await middleware(
      new NextRequest("https://vendor.example.test/en/reset-password/confirm"),
    );
    expect(response.cookies.get("synthetic-refresh")?.value).toBe("fixture");
  });
});

function getScriptSrc(csp: string | null): string | undefined {
  return csp?.split("; ").find((directive) => directive.startsWith("script-src"));
}

function expectNonceReportOnlyCsp(response: NextResponse): void {
  const csp = response.headers.get(CSP_REPORT_ONLY_HEADER);
  const scriptSrc = getScriptSrc(csp);

  expect(csp).toBeTruthy();
  expect(csp).not.toContain(CSP_NONCE_PLACEHOLDER);
  expect(csp).not.toContain("lenco.co");
  expect(scriptSrc).toMatch(/'nonce-[^']+'/);
  expect(scriptSrc).toContain("'strict-dynamic'");
  expect(scriptSrc).not.toContain("'unsafe-inline'");
  expect(scriptSrc).not.toContain("'unsafe-eval'");
}

describe("vendor middleware CSP nonce", () => {
  beforeEach(() => {
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockReturnValue(null);
  });

  it("adds a nonce-bearing report-only CSP to pass-through responses", async () => {
    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en"));

    expect(response.status).toBe(200);
    expectNonceReportOnlyCsp(response);
  });

  it("adds a nonce-bearing report-only CSP to login redirects", async () => {
    resolveGatedRedirectMock.mockReturnValue("login");

    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en/listings"));

    expect(response.status).toBe(307);
    expectNonceReportOnlyCsp(response);
  });

  it("sends authenticated non-vendors to onboarding instead of granting access", async () => {
    resolveGatedRedirectMock.mockReturnValue("onboarding");

    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en/listings"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://vendor.vergeo5.com/en/onboarding");
    expectNonceReportOnlyCsp(response);
  });
});

describe("vendor middleware — /health exemption", () => {
  beforeEach(() => {
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockReturnValue("login");
  });

  it("HEALTH-10 (vendor): /health is reachable unauthenticated without consulting the vendor role gate", async () => {
    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en/health"));

    expect(response.status).toBe(200);
    expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
  });

  it("still redirects an unauthenticated request to a protected route", async () => {
    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en/listings"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://vendor.vergeo5.com/en/login");
    expect(resolveGatedRedirectMock).toHaveBeenCalledWith(
      "vendor",
      "/en/listings",
      expect.anything(),
      null,
      [],
    );
  });

  it("does not exempt a path that merely starts with health", async () => {
    const response = await middleware(new NextRequest("https://vendor.vergeo5.com/en/healthcheck"));

    expect(resolveGatedRedirectMock).toHaveBeenCalledWith(
      "vendor",
      "/en/healthcheck",
      expect.anything(),
      null,
      [],
    );
    expect(response.status).toBe(307);
  });
});
