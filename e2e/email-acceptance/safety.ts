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

export function stagingOrigin(raw: string | undefined, name: string): string {
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
    new RegExp(
      `^convergeo-${portal}-[a-z0-9-]+-vergeo-projects\\.vercel\\.app$`,
    ).test(host);
  if (
    url.protocol !== "https:" ||
    PROD_HOSTS.has(host) ||
    !trustedHost ||
    url.hostname === "localhost" ||
    url.hostname === "127.0.0.1" ||
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
    throw new Error(
      "E2E_EXPECT_SHA must bind the diagnostic to a full candidate SHA",
    );
  }
  if (requireProbe && env.E2E_EMAIL_PROBE_SHA !== env.E2E_EXPECT_SHA) {
    throw new Error(
      "strict customer and vendor SHA probes must pass before email acceptance",
    );
  }
  const customerOrigin = stagingOrigin(env.E2E_BASE_URL, "E2E_BASE_URL");
  const vendorOrigin = stagingOrigin(
    env.E2E_VENDOR_BASE_URL,
    "E2E_VENDOR_BASE_URL",
  );
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
  if (url.protocol !== "https:") return false;
  if (url.origin === portalOrigin) return method === "GET" || method === "HEAD";
  if (url.origin === STAGING_AUTH_ORIGIN) {
    if (method === "POST") {
      return (
        path === "/auth/v1/token" &&
        url.searchParams.get("grant_type") === "password"
      );
    }
    return (
      (method === "GET" || method === "HEAD") &&
      (path.startsWith("/auth/v1/") || path.startsWith("/rest/v1/"))
    );
  }
  if (url.origin === STAGING_API_ORIGIN) {
    return (
      (method === "GET" || method === "HEAD") &&
      !/\/(?:payments|payouts|orders|checkout|internal|webhooks)(?:\/|$)/.test(
        path,
      )
    );
  }
  return (
    allowStatic &&
    STATIC_ORIGINS.has(url.origin) &&
    method === "GET" &&
    ["image", "font", "stylesheet"].includes(resourceType)
  );
}

/** Check after navigation and immediately before filling a password. */
export function assertExpectedLoginLocation(
  actual: string,
  expectedOrigin: string,
): void {
  let url: URL;
  try {
    url = new URL(actual);
  } catch {
    throw new Error("email login did not land on the approved portal");
  }
  if (url.origin !== expectedOrigin || url.pathname !== "/en/login") {
    throw new Error(
      "email login redirected away from the approved portal login",
    );
  }
}

export function isPasswordTokenRequest(url: URL, method: string): boolean {
  return (
    method === "POST" &&
    url.pathname.toLowerCase() === "/auth/v1/token" &&
    url.searchParams.get("grant_type") === "password"
  );
}
