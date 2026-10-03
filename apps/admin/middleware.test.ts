import {
  CSP_NONCE_PLACEHOLDER,
  CSP_REPORT_ONLY_HEADER,
  createPortalRedirect,
  getLocaleFromPath,
  resolveGatedRedirect,
  updateSession,
} from "@vergeo/auth/middleware";
import { LOCALES } from "@vergeo/i18n";
import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authMocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  getClaims: vi.fn(),
  getSession: vi.fn(),
}));

// The SDK belongs to the auth workspace; resolve its fixture from that owner too.
vi.mock("../../packages/auth/node_modules/@supabase/ssr", () => ({
  createServerClient: vi.fn(() => ({ auth: authMocks })),
}));

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

vi.mock("@vergeo/auth/middleware", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/auth/middleware")>();
  return {
    ...actual,
    createLoginRedirect: vi.fn(),
    createPortalRedirect: vi.fn(
      (kind: "login" | "onboarding" | "permission-denied", request: NextRequest, locale: string) =>
        NextResponse.redirect(
          new URL(`/${locale}/${kind === "login" ? "login" : kind}`, request.url),
        ),
    ),
    getLocaleFromPath: vi.fn(() => "en"),
    mergeSessionCookies: vi.fn((_source: Response, target: Response) => target),
    resolveGatedRedirect: resolveGatedRedirectMock,
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
const { verifyCfAccessAssertionMock, resolveGatedRedirectMock } = vi.hoisted(() => ({
  verifyCfAccessAssertionMock: vi.fn(),
  resolveGatedRedirectMock: vi.fn((): "login" | "onboarding" | "permission-denied" | null => null),
}));

vi.mock("./lib/cf-access", () => ({
  verifyCfAccessAssertion: verifyCfAccessAssertionMock,
}));

import { isAdminPasswordRecoveryPath } from "./lib/password-recovery-path";
import middleware, {
  createCfAccessForbiddenResponse,
  hasCfAccessJwtAssertion,
  isProductionCfAccessRequired,
} from "./middleware";

describe("recovery composition with current verified-claims authorization", () => {
  const defaultUpdateSession = vi.mocked(updateSession).getMockImplementation()!;
  const defaultCreatePortalRedirect = vi.mocked(createPortalRedirect).getMockImplementation()!;
  const defaultGetLocaleFromPath = vi.mocked(getLocaleFromPath).getMockImplementation()!;

  beforeEach(async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test-anon-key");
    verifyCfAccessAssertionMock.mockReset();
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: true });
    authMocks.getUser.mockReset();
    authMocks.getClaims.mockReset();
    authMocks.getSession.mockReset();
    authMocks.getUser.mockResolvedValue({
      data: {
        user: {
          id: "fixture-user",
          app_metadata: { roles: ["admin"] },
          user_metadata: { roles: ["admin"] },
        },
      },
    });
    authMocks.getClaims.mockResolvedValue({
      data: { claims: { app_metadata: { roles: ["customer"] } } },
      error: null,
    });
    const actual =
      await vi.importActual<typeof import("@vergeo/auth/middleware")>("@vergeo/auth/middleware");
    vi.mocked(updateSession).mockImplementation(actual.updateSession);
    resolveGatedRedirectMock.mockImplementation(actual.resolveGatedRedirect);
    vi.mocked(createPortalRedirect).mockImplementation(actual.createPortalRedirect);
    vi.mocked(getLocaleFromPath).mockImplementation(actual.getLocaleFromPath);
  });

  afterEach(() => {
    vi.mocked(updateSession).mockImplementation(defaultUpdateSession);
    vi.mocked(createPortalRedirect).mockImplementation(defaultCreatePortalRedirect);
    vi.mocked(getLocaleFromPath).mockImplementation(defaultGetLocaleFromPath);
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockReturnValue(null);
    vi.unstubAllEnvs();
  });

  it.each([
    "/fr/orders",
    "/fr/reset-password/admin",
    "/fr/reset-password/confirm/admin",
    "/fr/reset-password-other",
  ])(
    "denies stale User metadata and production bypass outside exact recovery: %s",
    async (path) => {
      const response = await middleware(new NextRequest(`https://admin.example.test${path}`));
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "https://admin.example.test/fr/permission-denied",
      );
      expect(authMocks.getClaims).toHaveBeenCalledOnce();
      expect(authMocks.getSession).not.toHaveBeenCalled();
      expect(resolveGatedRedirect).toHaveBeenCalledWith(
        "admin",
        path,
        LOCALES,
        expect.objectContaining({ id: "fixture-user" }),
        ["customer"],
        { adminBypass: false },
      );
    },
  );

  it.each(["missing", "error", "thrown", "malformed", "user_metadata"])(
    "keeps protected routes closed when verified claims are %s",
    async (kind) => {
      if (kind === "thrown") authMocks.getClaims.mockRejectedValue(new Error("fixture"));
      else
        authMocks.getClaims.mockResolvedValue({
          data:
            kind === "missing"
              ? null
              : {
                  claims:
                    kind === "user_metadata"
                      ? { user_metadata: { roles: ["admin"] } }
                      : { app_metadata: { roles: kind === "error" ? ["admin"] : "admin" } },
                },
          error: kind === "error" ? { message: "fixture" } : null,
        });
      const response = await middleware(new NextRequest("https://admin.example.test/en/orders"));
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "https://admin.example.test/en/permission-denied",
      );
      expect(authMocks.getSession).not.toHaveBeenCalled();
    },
  );

  it("uses verified admin claims even when the User object has no roles", async () => {
    authMocks.getUser.mockResolvedValue({
      data: { user: { id: "fixture-admin", app_metadata: {} } },
    });
    authMocks.getClaims.mockResolvedValue({
      data: { claims: { app_metadata: { roles: ["admin"] } } },
      error: null,
    });
    const response = await middleware(new NextRequest("https://admin.example.test/en/orders"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(authMocks.getClaims).toHaveBeenCalledOnce();
    expect(authMocks.getSession).not.toHaveBeenCalled();
  });

  it("ignores raw session cookies and hostile next redirects on a protected lookalike route", async () => {
    authMocks.getUser.mockResolvedValue({ data: { user: null } });
    authMocks.getClaims.mockResolvedValue({ data: null, error: null });
    const response = await middleware(
      new NextRequest(
        "https://admin.example.test/fr/reset-password/confirm/admin?next=https://evil.example.test",
        { headers: { cookie: "sb-fixture-auth-token=fixture-admin-session" } },
      ),
    );
    const location = new URL(response.headers.get("location")!);
    expect(response.status).toBe(307);
    expect(location.origin).toBe("https://admin.example.test");
    expect(location.pathname).toBe("/fr/login");
    expect(location.searchParams.get("next")).toBe("/fr/reset-password/confirm/admin");
    expect(authMocks.getSession).not.toHaveBeenCalled();
  });

  it.each(["/en/reset-password", "/fr/reset-password/confirm"])(
    "allows only recovery with unavailable claims after Cloudflare verification: %s",
    async (path) => {
      authMocks.getUser.mockResolvedValue({ data: { user: null } });
      authMocks.getClaims.mockRejectedValue(new Error("fixture"));
      const response = await middleware(new NextRequest(`https://admin.example.test${path}`));
      expect(response.status).toBe(200);
      expect(verifyCfAccessAssertionMock).toHaveBeenCalledOnce();
      expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
      expect(authMocks.getSession).not.toHaveBeenCalled();
    },
  );

  it.each(["assertion_missing", "verification_failed", "audience_missing", "issuer_missing"])(
    "fails closed on recovery when Cloudflare returns %s",
    async (reason) => {
      verifyCfAccessAssertionMock.mockResolvedValue({ ok: false, reason });
      const response = await middleware(
        new NextRequest("https://admin.example.test/en/reset-password/confirm?code=fixture"),
      );
      expect(response.status).toBe(403);
      expect(response.headers.get("location")).toBeNull();
      expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
    },
  );
});

describe("admin password recovery gate", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", undefined);
    verifyCfAccessAssertionMock.mockReset();
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: true });
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockReturnValue("login");
  });

  afterEach(() => vi.unstubAllEnvs());

  it.each(
    LOCALES.flatMap((locale) => [
      `/${locale}/reset-password`,
      `/${locale}/reset-password/confirm`,
      `/${locale}/reset-password/`,
      `/${locale}/reset-password/confirm/`,
    ]),
  )("allows recovery without an app session after CF Access: %s", async (path) => {
    const response = await middleware(
      new NextRequest(`https://admin.example.test${path}?code=fixture`),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(verifyCfAccessAssertionMock).toHaveBeenCalledOnce();
    expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
  });

  it.each(["/en/reset-password", "/en/reset-password/confirm"])(
    "keeps CF Access fail-closed on %s",
    async (path) => {
      verifyCfAccessAssertionMock.mockResolvedValue({
        ok: false,
        reason: "assertion_missing",
      });
      const response = await middleware(new NextRequest(`https://admin.example.test${path}`));
      expect(response.status).toBe(403);
      expect(resolveGatedRedirectMock).not.toHaveBeenCalled();
    },
  );

  it.each([
    "/en",
    "/en/reset-password/admin",
    "/en/reset-password/confirm/admin",
    "/en/reset-password-other",
  ])("preserves role gating outside the exact recovery routes: %s", async (path) => {
    resolveGatedRedirectMock.mockReturnValue("permission-denied");
    const response = await middleware(new NextRequest(`https://admin.example.test${path}`));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://admin.example.test/en/permission-denied",
    );
    expect(resolveGatedRedirectMock).toHaveBeenCalledOnce();
  });

  it.each([
    "/xx/reset-password",
    "/reset-password",
    "/en/reset-password//",
    "/en/reset-password/confirm-extra",
  ])("does not classify unsupported or lookalike paths as recovery: %s", (path) => {
    expect(isAdminPasswordRecoveryPath(path)).toBe(false);
  });
});

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
    resolveGatedRedirectMock.mockReset();
    resolveGatedRedirectMock.mockReturnValue(null);
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

  it("keeps Cloudflare Access in front of admin role checks", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resolveGatedRedirectMock.mockReturnValue("permission-denied");
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: false, reason: "assertion_missing" });

    const response = await middleware(new NextRequest("https://admin.vergeo5.com/en"));

    expect(response.status).toBe(403);
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not grant admin access to an authenticated non-admin after CF Access", async () => {
    vi.stubEnv("NODE_ENV", "production");
    verifyCfAccessAssertionMock.mockResolvedValue({ ok: true, payload: { sub: "cf-user" } });
    resolveGatedRedirectMock.mockReturnValue("permission-denied");

    const request = new NextRequest("https://admin.vergeo5.com/en", {
      headers: { "cf-access-jwt-assertion": "valid.jwt.value" },
    });
    const response = await middleware(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://admin.vergeo5.com/en/permission-denied");
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
    expect(config.matcher).toEqual(["/api/csp-report", "/", "/(en|bem|nya|fr|zh)/:path*"]);
  });
});
