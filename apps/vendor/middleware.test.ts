import { CSP_NONCE_PLACEHOLDER, CSP_REPORT_ONLY_HEADER } from "@vergeo/auth/middleware";
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

import middleware from "./middleware";

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
