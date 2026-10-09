import { SEED } from "../fixtures/seed.generated.ts";

const PROD_HOSTS = new Set([
  "vergeo5.com",
  "www.vergeo5.com",
  "vendor.vergeo5.com",
  "admin.vergeo5.com",
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

export function emailAcceptanceConfig(env: Record<string, string | undefined>) {
  if (!/^[0-9a-f]{40}$/.test(env.E2E_EXPECT_SHA ?? "")) {
    throw new Error(
      "E2E_EXPECT_SHA must bind the diagnostic to a full candidate SHA",
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

/** Refuse provider, order, and outbound calls in the email-only diagnostic. */
export function forbiddenEmailAcceptanceRequest(url: URL): boolean {
  const path = url.pathname.toLowerCase();
  const host = url.hostname.toLowerCase();
  return (
    host === "api.lenco.co" ||
    host.endsWith(".lenco.co") ||
    host === "api.africastalking.com" ||
    host.endsWith(".africastalking.com") ||
    host.includes("waha") ||
    host.endsWith(".whatsapp.com") ||
    path === "/auth/v1/otp" ||
    path.includes("/functions/v1/send-sms-otp") ||
    path.includes("/payments/") ||
    path.includes("/payouts/") ||
    path.includes("/orders") ||
    path.includes("/checkout/") ||
    path.includes("/internal/dispatch") ||
    path.includes("/webhooks/")
  );
}
