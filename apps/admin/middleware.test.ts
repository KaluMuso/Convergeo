import { CSP_NONCE_PLACEHOLDER, CSP_REPORT_ONLY_HEADER } from "@vergeo/auth/middleware";
import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

vi.mock("@vergeo/auth/middleware", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/auth/middleware")>();
  return {
    ...actual,
    createLoginRedirect: vi.fn(),
    getLocaleFromPath: vi.fn(() => "en"),
    mergeSessionCookies: vi.fn((_source: Response, target: Response) => target),
    shouldRedirectToLogin: vi.fn(() => false),
    updateSession: vi.fn(async () => ({
      response: NextResponse.next(),
      user: null,
      roles: [],
    })),
  };
});

// Cryptographic CF Access verification is unit-tested in ./lib/cf-access.test.ts.
// Here we mock it to assert the middleware's wiring: prod fails closed on a non-ok
// result, passes on ok, and skips verification entirely outside production.
const { verifyCfAccessAssertionMock } = vi.hoisted(() => ({
  verifyCfAccessAssertionMock: vi.fn(),
}));

vi.mock("./lib/cf-access", () => ({
  verifyCfAccessAssertion: verifyCfAccessAssertionMock,
}));

import middleware, {
  createCfAccessForbiddenResponse,
  hasCfAccessJwtAssertion,
  isProductionCfAccessRequired,
} from "./middleware";

describe("admin middleware CF Access helpers", () => {
  const originalNodeEnv = process.env.NODE_ENV;
  const originalBypass = process.env.NEXT_PUBLIC_ADMIN_BYPASS;

  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "test");
    vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", undefined);
  });

  afterEach(() => {
    vi.stubEnv("NODE_ENV", originalNodeEnv ?? "test");
    if (originalBypass === undefined) {
      delete process.env.NEXT_PUBLIC_ADMIN_BYPASS;
    } else {
      vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", originalBypass);
    }
  });

  it("requires CF Access only in production without bypass", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(isProductionCfAccessRequired()).toBe(false);

    vi.stubEnv("NODE_ENV", "production");
    expect(isProductionCfAccessRequired()).toBe(true);

    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", "true");
    expect(isProductionCfAccessRequired()).toBe(false);
  });

  it("detects Cf-Access-Jwt-Assertion header presence", () => {
    const withHeader = new NextRequest("https://admin.vergeo5.com/en", {
      headers: { "cf-access-jwt-assertion": "a.b.c" },
    });
    const withoutHeader = new NextRequest("https://admin.vergeo5.com/en");

    expect(hasCfAccessJwtAssertion(withHeader)).toBe(true);
    expect(hasCfAccessJwtAssertion(withoutHeader)).toBe(false);
  });

  it("returns a 403 forbidden response for missing CF Access", () => {
    const response = createCfAccessForbiddenResponse();
    expect(response.status).toBe(403);
  });
});

describe("admin middleware — CF Access enforcement", () => {
  beforeEach(() => {
    verifyCfAccessAssertionMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns 403 in production when assertion verification fails", async () => {
    vi.stubEnv("NODE_ENV", "production");
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: false, reason: "verification_failed" });

    const request = new NextRequest("https://admin.vergeo5.com/en", {
      headers: { "cf-access-jwt-assertion": "tampered.jwt.value" },
    });
    const response = await middleware(request);

    expect(response.status).toBe(403);
    expect(verifyCfAccessAssertionMock).toHaveBeenCalledWith("tampered.jwt.value");
  });

  it("returns 403 in production when the assertion header is absent", async () => {
    vi.stubEnv("NODE_ENV", "production");
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: false, reason: "assertion_missing" });

    const request = new NextRequest("https://admin.vergeo5.com/en");
    const response = await middleware(request);

    expect(response.status).toBe(403);
    expect(verifyCfAccessAssertionMock).toHaveBeenCalledWith(null);
  });

  it("proceeds past the CF Access gate in production when verification succeeds", async () => {
    vi.stubEnv("NODE_ENV", "production");
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: true, payload: { sub: "cf-user" } });

    const request = new NextRequest("https://admin.vergeo5.com/en", {
      headers: { "cf-access-jwt-assertion": "valid.jwt.value" },
    });
    const response = await middleware(request);

    expect(response.status).toBe(200);
    expect(verifyCfAccessAssertionMock).toHaveBeenCalledWith("valid.jwt.value");
  });

  it("does not verify (or block) outside production", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const request = new NextRequest("https://admin.vergeo5.com/en", {
      headers: { "cf-access-jwt-assertion": "anything" },
    });
    const response = await middleware(request);

    expect(response.status).toBe(200);
    expect(verifyCfAccessAssertionMock).not.toHaveBeenCalled();
  });

  it("substitutes a report-only CSP nonce without enabling unsafe script directives", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const response = await middleware(new NextRequest("https://admin.vergeo5.com/en"));
    const csp = response.headers.get(CSP_REPORT_ONLY_HEADER);
    const scriptSrc = csp?.split("; ").find((directive) => directive.startsWith("script-src"));

    expect(csp).toBeTruthy();
    expect(csp).not.toContain(CSP_NONCE_PLACEHOLDER);
    expect(scriptSrc).toMatch(/'nonce-[^']+'/);
    expect(scriptSrc).toContain("'strict-dynamic'");
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
  });
});

describe("admin middleware matrix", () => {
  it("documents locale matcher coverage for all supported locales", async () => {
    const { config } = await import("./middleware");
    expect(config.matcher).toEqual(["/", "/(en|bem|nya|fr|zh)/:path*"]);
  });
});
