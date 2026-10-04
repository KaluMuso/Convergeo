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
import middleware from "./middleware";

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
      const response = await middleware(new NextRequest("https://vendor.example.test/en/listings"));
      expect(response.status).toBe(role === "vendor" ? 200 : 307);
      expect(response.headers.get("location")).toBe(
        role === "vendor" ? null : "https://vendor.example.test/en/onboarding",
      );
      expectNonceReportOnlyCsp(response);
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
