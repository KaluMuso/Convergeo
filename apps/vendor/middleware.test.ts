import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

const { resolveGatedRedirectMock } = vi.hoisted(() => ({
  resolveGatedRedirectMock: vi.fn(
    (): "login" | "onboarding" | "permission-denied" | null => "login",
  ),
}));

vi.mock("@vergeo/auth/middleware", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/auth/middleware")>();
  return {
    ...actual,
    createPortalRedirect: vi.fn(
      (kind: "login" | "onboarding" | "permission-denied", request: NextRequest, locale: string) =>
        NextResponse.redirect(new URL(`/${locale}/${kind}`, request.url)),
    ),
    getLocaleFromPath: vi.fn(() => "en"),
    mergeSessionCookies: vi.fn((_source: Response, target: Response) => target),
    resolveGatedRedirect: resolveGatedRedirectMock,
    updateSession: vi.fn(async () => ({
      response: NextResponse.next(),
      user: null,
      roles: [],
    })),
  };
});

import middleware from "./middleware";

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
    resolveGatedRedirectMock.mockReturnValue("login");
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
