import { Buffer } from "node:buffer";

import { SEED } from "../fixtures/seed.generated.ts";

const PROD_HOSTS = new Set([
  "vergeo5.com",
  "www.vergeo5.com",
  "vendor.vergeo5.com",
  "admin.vergeo5.com",
]);
export const STAGING_AUTH_ORIGIN = "https://iyasmrmbcrvlfxpzescb.supabase.co";
const STAGING_API_ORIGIN = "https://api.staging.vergeo5.com";
const STATIC_ORIGINS = new Set([
  "https://res.cloudinary.com",
  "https://fonts.googleapis.com",
  "https://fonts.gstatic.com",
]);

export function stagingOrigin(
  raw: string | undefined,
  name: "E2E_BASE_URL" | "E2E_VENDOR_BASE_URL",
): string {
  if (!raw) throw new Error(`${name} is required for email acceptance`);
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} must be a valid HTTPS staging URL`);
  }
  const portal = name === "E2E_BASE_URL" ? "customer" : "vendor";
  const host = url.hostname.toLowerCase();
  const trustedHost =
    host === `${portal}.staging.vergeo5.com` ||
    new RegExp(`^convergeo-${portal}-[a-z0-9-]+-vergeo-projects\\.vercel\\.app$`).test(host);
  if (
    url.protocol !== "https:" ||
    PROD_HOSTS.has(host) ||
    !trustedHost ||
    url.hostname === "localhost" ||
    url.hostname === "127.0.0.1" ||
    url.port ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(`${name} must be a clean HTTPS staging origin`);
  }
  return url.origin;
}

export function emailAcceptanceConfig(
  env: Record<string, string | undefined>,
  { requireProbe = true }: { requireProbe?: boolean } = {},
) {
  if (!/^[0-9a-f]{40}$/.test(env.E2E_EXPECT_SHA ?? "")) {
    throw new Error("E2E_EXPECT_SHA must bind the diagnostic to a full candidate SHA");
  }
  if (requireProbe && env.E2E_EMAIL_PROBE_SHA !== env.E2E_EXPECT_SHA) {
    throw new Error("strict customer and vendor SHA probes must pass before email acceptance");
  }
  const customerOrigin = stagingOrigin(env.E2E_BASE_URL, "E2E_BASE_URL");
  const vendorOrigin = stagingOrigin(env.E2E_VENDOR_BASE_URL, "E2E_VENDOR_BASE_URL");
  if (customerOrigin === vendorOrigin) {
    throw new Error("customer and vendor origins must be separate");
  }
  const customerPassword = env.E2E_CUSTOMER_EMAIL_PASSWORD ?? "";
  const vendorPassword = env.E2E_VENDOR_EMAIL_PASSWORD ?? "";
  if (customerPassword.length < 8 || vendorPassword.length < 8) {
    throw new Error("both synthetic email passwords are required");
  }
  return {
    customer: {
      origin: customerOrigin,
      email: `${SEED.personas.customer.handle}@staging.vergeo5.test`,
      password: customerPassword,
      next: "/en/account",
    },
    vendor: {
      origin: vendorOrigin,
      email: `${SEED.personas.vendor.handle}@staging.vergeo5.test`,
      password: vendorPassword,
      next: "/en/services",
    },
  };
}

/** Only the exact portal, staging Auth/API, and non-sensitive static assets may load. */
export function allowedEmailAcceptanceRequest(
  url: URL,
  method: string,
  resourceType: string,
  portalOrigin: string,
  allowStatic = true,
): boolean {
  const path = url.pathname.toLowerCase();
  const readOnly = method === "GET" || method === "HEAD";
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    url.hash ||
    /[%\\]/.test(path) ||
    [...url.searchParams.keys()].some((key) =>
      /password|token|secret|code|authorization/i.test(key),
    )
  )
    return false;
  if (
    /\/(?:payments|payouts|orders|checkout|internal|webhooks|recover|reset|signup|signout|logout|otp|verify|resend)(?:[-/]|$)/.test(
      path,
    )
  ) {
    return false;
  }
  if (url.origin === portalOrigin) return readOnly;
  if (url.origin === STAGING_AUTH_ORIGIN) {
    if (method === "POST") return isExactPasswordTokenRequest(url, method);
    return readOnly && ((path === "/auth/v1/user" && !url.search) || path.startsWith("/rest/v1/"));
  }
  if (url.origin === STAGING_API_ORIGIN) return readOnly;
  return (
    allowStatic &&
    STATIC_ORIGINS.has(url.origin) &&
    method === "GET" &&
    ["image", "font", "stylesheet"].includes(resourceType)
  );
}

/** Check after navigation and immediately before filling a password. */
export function assertExpectedLoginLocation(actual: string, expectedOrigin: string): void {
  let url: URL;
  try {
    url = new URL(actual);
  } catch {
    throw new Error("email login did not land on the approved portal");
  }
  if (
    url.origin !== expectedOrigin ||
    url.pathname !== "/en/login" ||
    url.username ||
    url.password ||
    url.hash ||
    url.port
  ) {
    throw new Error("email login redirected away from the approved portal login");
  }
}

export function isPasswordTokenRequest(url: URL, method: string): boolean {
  return (
    method === "POST" &&
    url.pathname.toLowerCase() === "/auth/v1/token" &&
    url.searchParams.get("grant_type") === "password"
  );
}

/** Exact HTTPS password exchange; refresh, OTP and recovery requests are excluded. */
export function isExactPasswordTokenRequest(url: URL, method: string): boolean {
  return (
    url.origin === STAGING_AUTH_ORIGIN &&
    !url.username &&
    !url.password &&
    !url.port &&
    !url.hash &&
    method === "POST" &&
    url.pathname === "/auth/v1/token" &&
    url.search === "?grant_type=password"
  );
}

export function assertEmailCaptureDisabled(env: Record<string, string | undefined>): void {
  if (env.PLAYWRIGHT_NO_COPY_PROMPT !== "1") {
    throw new Error("email diagnostic requires failure snapshots disabled");
  }
}

export function assertEmptyEmailContext(state: { cookies: unknown[]; origins: unknown[] }): void {
  if (state.cookies.length || state.origins.length) {
    throw new Error("email diagnostic requires an empty isolated context");
  }
}

/** Receipt consistency/expiry only. Protected server routes remain the auth authority. */
export function assertFreshPasswordReceipt(
  raw: unknown,
  expectedEmail: string,
  nowSeconds = Math.floor(Date.now() / 1000),
  attemptStartedAt = nowSeconds,
): void {
  try {
    if (!raw || typeof raw !== "object") throw new Error();
    const body = raw as Record<string, unknown>;
    const user = body.user as { id?: unknown; email?: unknown } | undefined;
    if (
      !user ||
      typeof user.id !== "string" ||
      !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(user.id) ||
      user.email !== expectedEmail ||
      body.token_type !== "bearer" ||
      !Number.isSafeInteger(body.expires_in) ||
      typeof body.expires_in !== "number" ||
      body.expires_in <= 0 ||
      typeof body.access_token !== "string" ||
      body.access_token.length > 16384 ||
      !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(body.access_token)
    )
      throw new Error();
    const claims = JSON.parse(
      Buffer.from(body.access_token.split(".")[1], "base64url").toString("utf8"),
    );
    if (
      claims.iss !== `${STAGING_AUTH_ORIGIN}/auth/v1` ||
      claims.sub !== user.id ||
      claims.aud !== "authenticated" ||
      !Number.isSafeInteger(claims.exp) ||
      claims.exp <= nowSeconds ||
      !Number.isSafeInteger(claims.iat) ||
      !Number.isSafeInteger(attemptStartedAt) ||
      attemptStartedAt > nowSeconds ||
      nowSeconds - attemptStartedAt > 60 ||
      claims.iat < attemptStartedAt - 60 ||
      claims.iat > nowSeconds + 60 ||
      claims.exp <= claims.iat
    )
      throw new Error();
  } catch {
    throw new Error("email diagnostic did not receive a fresh staging password session");
  }
}
