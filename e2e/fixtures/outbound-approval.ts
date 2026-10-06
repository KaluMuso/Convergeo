/** Run-scoped consent and target binding for E2E calls that can send OTP or initiate money. */
import type { Page, Route } from "@playwright/test";

export type OutboundIntent = "otp" | "momo" | "paid-ticket";

type ApprovalOptions = {
  persona?: "customer" | "vendor";
  recipientPhone?: string;
  authOrigin?: string;
  apiOrigin?: string;
};
type ApprovalEnv = Record<string, string | undefined>;

const SANDBOX_PROJECT = "iyasmrmbcrvlfxpzescb";
const SANDBOX_AUTH_ORIGIN = `https://${SANDBOX_PROJECT}.supabase.co`;
const STAGING_API_ORIGIN = "https://api.staging.vergeo5.com";
const CHECKOUT_WRITES = new Set([
  "/checkout/session",
  "/checkout/steps/contact",
  "/checkout/steps/fulfilment",
  "/checkout/steps/payment",
]);

function value(env: ApprovalEnv, key: string): string {
  return (env[key] ?? "").trim();
}

function exactOrigin(raw: string): string | null {
  try {
    const url = new URL(raw);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    )
      return null;
    return url.origin;
  } catch {
    return null;
  }
}

function nationalPhone(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  return /^(?:\+260|260|0)?([79]\d{8})$/.exec(raw.trim())?.[1] ?? null;
}

/** Playwright invokes a route handler only for the first URL in a redirect chain. */
async function fulfillWithoutRedirect(route: Route): Promise<void> {
  let response;
  try {
    response = await route.fetch({ maxRedirects: 0 });
  } catch {
    await route.abort("blockedbyclient");
    return;
  }
  if (response.status() >= 300 && response.status() < 400) {
    await route.abort("blockedbyclient");
    return;
  }
  await route.fulfill({ response });
}

function missingCommerceTarget(env: ApprovalEnv, apiOrigin?: string): string[] {
  const missing: string[] = [];
  const customerOrigin = exactOrigin(value(env, "E2E_BASE_URL"));
  const customerHost = customerOrigin ? new URL(customerOrigin).hostname : "";
  if (
    !customerOrigin ||
    !(
      /^customer\.staging\.vergeo5\.com$/.test(customerHost) ||
      /^convergeo-customer-(?![a-z0-9-]*(?:prod|master))[a-z0-9-]+-vergeo-projects\.vercel\.app$/.test(
        customerHost,
      )
    ) ||
    value(env, "E2E_APPROVED_CUSTOMER_ORIGIN") !== customerOrigin
  )
    missing.push("E2E_APPROVED_CUSTOMER_ORIGIN");
  if (
    value(env, "STAGING_API_HOST") !== "api.staging.vergeo5.com" ||
    value(env, "E2E_APPROVED_API_ORIGIN") !== STAGING_API_ORIGIN ||
    (apiOrigin && exactOrigin(apiOrigin) !== STAGING_API_ORIGIN)
  )
    missing.push("E2E_APPROVED_API_ORIGIN");
  return missing;
}

export function missingOutboundApproval(
  intent: OutboundIntent,
  env: ApprovalEnv = process.env,
  options: ApprovalOptions = {},
): string[] {
  const missing: string[] = [];
  const approvalFlag = {
    otp: "E2E_OTP_RECIPIENT_APPROVED",
    momo: "E2E_MOMO_PROVIDER_APPROVED",
    "paid-ticket": "E2E_PAID_TICKET_PROVIDER_APPROVED",
  }[intent];
  if (value(env, approvalFlag) !== "1") missing.push(approvalFlag);
  for (const [approval, actual] of [
    ["E2E_APPROVED_RUN_ID", "GITHUB_RUN_ID"],
    ["E2E_APPROVED_RUN_ATTEMPT", "GITHUB_RUN_ATTEMPT"],
  ]) {
    if (!value(env, actual) || value(env, approval) !== value(env, actual)) missing.push(approval);
  }
  if (
    value(env, "E2E_STAGING_SETUP") !== "true" ||
    value(env, "E2E_STRICT_SHA") !== "true" ||
    !/^[a-f0-9]{40}$/.test(value(env, "E2E_EXPECT_SHA"))
  )
    missing.push("verified staging handoff");
  if (value(env, "STAGING_SUPABASE_PROJECT_ID") !== SANDBOX_PROJECT)
    missing.push("STAGING_SUPABASE_PROJECT_ID");
  if (exactOrigin(value(env, "STAGING_SUPABASE_URL")) !== SANDBOX_AUTH_ORIGIN)
    missing.push("STAGING_SUPABASE_URL");
  if (options.authOrigin && exactOrigin(options.authOrigin) !== SANDBOX_AUTH_ORIGIN)
    missing.push("sandbox Auth origin");

  if (intent === "otp") {
    const key =
      options.persona === "vendor" ? "E2E_APPROVED_VENDOR_PHONE" : "E2E_APPROVED_CUSTOMER_PHONE";
    if (!options.recipientPhone || value(env, key) !== options.recipientPhone) missing.push(key);
    return missing;
  }

  if (value(env, "LENCO_SANDBOX") !== "1" || value(env, "LENCO_ENV") !== "sandbox")
    missing.push("LENCO_SANDBOX/LENCO_ENV");
  if (!value(env, "LENCO_SANDBOX_SECRET_KEY")) missing.push("LENCO_SANDBOX_SECRET_KEY");
  if (
    !value(env, "LENCO_SANDBOX_MOMO_NUMBER") ||
    value(env, "E2E_APPROVED_MOMO_NUMBER") !== value(env, "LENCO_SANDBOX_MOMO_NUMBER")
  )
    missing.push("E2E_APPROVED_MOMO_NUMBER");
  if (value(env, "E2E_APPROVED_MOMO_RAIL") !== "mtn") missing.push("E2E_APPROVED_MOMO_RAIL");
  missing.push(...missingCommerceTarget(env, options.apiOrigin));
  return missing;
}

export function missingCodApproval(
  recipientPhone: string,
  env: ApprovalEnv = process.env,
): string[] {
  return [
    ...missingOutboundApproval("otp", env, { persona: "customer", recipientPhone }),
    ...missingCommerceTarget(env),
  ];
}

export function assertOutboundApproval(
  intent: OutboundIntent,
  options: ApprovalOptions = {},
  env: ApprovalEnv = process.env,
): void {
  const missing = missingOutboundApproval(intent, env, options);
  if (missing.length) throw new Error(`E2E outbound approval required: ${missing.join(", ")}`);
}

/** Block a misrouted browser checkout before the request reaches any API. */
export async function guardApprovedPaymentRequests(
  page: Page,
  intent: "momo" | "paid-ticket",
  env: ApprovalEnv = process.env,
): Promise<void> {
  assertOutboundApproval(intent, {}, env);
  await page.route(
    /\/(?:orders|checkout(?:\/[^?]+)?|payments\/(?:retry|card\/[^?]+)|tickets\/checkout)(?:\?|$)/,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const request = route.request();
      const url = new URL(request.url());
      const checkoutStep = CHECKOUT_WRITES.has(url.pathname);
      let body: Record<string, unknown>;
      try {
        const parsed: unknown = request.postDataJSON();
        if (parsed === null && url.pathname === "/checkout/session") body = {};
        else if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
          body = parsed as Record<string, unknown>;
        else throw new Error("body");
      } catch {
        await route.abort("blockedbyclient");
        return;
      }
      const payerRequired =
        url.pathname === "/orders" ||
        url.pathname === "/payments/retry" ||
        url.pathname === "/checkout/steps/payment";
      const wrongIntent =
        intent === "paid-ticket"
          ? url.pathname !== "/tickets/checkout"
          : !payerRequired && !checkoutStep;
      const payerMatches =
        nationalPhone(body.payer_number) !== null &&
        nationalPhone(body.payer_number) === nationalPhone(value(env, "E2E_APPROVED_MOMO_NUMBER"));
      const wrongRail =
        payerRequired &&
        (body.rail !== value(env, "E2E_APPROVED_MOMO_RAIL") ||
          ((url.pathname === "/orders" || url.pathname === "/checkout/steps/payment") &&
            body.method !== "momo"));
      if (
        missingOutboundApproval(intent, env, { apiOrigin: url.origin }).length ||
        wrongIntent ||
        url.pathname.startsWith("/payments/card/") ||
        (payerRequired && (!payerMatches || wrongRail))
      ) {
        await route.abort("blockedbyclient");
        return;
      }
      await fulfillWithoutRedirect(route);
    },
  );
}

/** Check the actual Auth host as well as the run-scoped synthetic recipient. */
export async function guardApprovedOtpRequests(
  page: Page,
  persona: "customer" | "vendor",
  recipientPhone: string,
  env: ApprovalEnv = process.env,
): Promise<void> {
  const options = { persona, recipientPhone };
  assertOutboundApproval("otp", options, env);
  await page.route(/\/auth\/v1\/otp(?:\?|$)/, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    let body: Record<string, unknown>;
    try {
      const parsed: unknown = route.request().postDataJSON();
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("body");
      body = parsed as Record<string, unknown>;
    } catch {
      await route.abort("blockedbyclient");
      return;
    }
    const authOrigin = new URL(route.request().url()).origin;
    if (
      missingOutboundApproval("otp", env, { ...options, authOrigin }).length ||
      nationalPhone(body.phone) === null ||
      nationalPhone(body.phone) !== nationalPhone(recipientPhone)
    ) {
      await route.abort("blockedbyclient");
      return;
    }
    await fulfillWithoutRedirect(route);
  });
}

/** COD may place an order, but an unexpected payment branch must never reach a provider. */
export async function guardCodWithoutProvider(
  page: Page,
  recipientPhone: string,
  env: ApprovalEnv = process.env,
): Promise<void> {
  const missing = missingCodApproval(recipientPhone, env);
  if (missing.length) throw new Error(`E2E COD approval required: ${missing.join(", ")}`);
  await page.route(
    /\/(?:orders|checkout(?:\/[^?]+)?|payments\/(?:retry|card\/[^?]+))(?:\?|$)/,
    async (route) => {
      const request = route.request();
      if (request.method() !== "POST") return route.continue();
      const url = new URL(request.url());
      if (missingCommerceTarget(env, url.origin).length) return route.abort("blockedbyclient");
      if (url.pathname === "/checkout/steps/payment") {
        try {
          const body: unknown = request.postDataJSON();
          if (
            body &&
            typeof body === "object" &&
            !Array.isArray(body) &&
            (body as Record<string, unknown>).method === "cod" &&
            (body as Record<string, unknown>).payer_number == null &&
            (body as Record<string, unknown>).rail == null
          )
            return fulfillWithoutRedirect(route);
        } catch {
          /* malformed payment selection fails closed */
        }
        return route.abort("blockedbyclient");
      }
      if (CHECKOUT_WRITES.has(url.pathname)) return fulfillWithoutRedirect(route);
      if (url.pathname !== "/orders") return route.abort("blockedbyclient");
      try {
        const body: unknown = request.postDataJSON();
        if (
          body &&
          typeof body === "object" &&
          !Array.isArray(body) &&
          (body as Record<string, unknown>).method === "cod"
        )
          return fulfillWithoutRedirect(route);
      } catch {
        /* malformed order fails closed */
      }
      return route.abort("blockedbyclient");
    },
  );
}

/** Keep browse-safe payment mocks from writing to a live checkout when a session exists. */
export async function blockUnapprovedCheckoutWrites(page: Page): Promise<void> {
  await page.route(
    /\/(?:auth\/v1\/otp|orders|checkout(?:\/[^?]+)?|payments\/[^?]+|tickets\/checkout)(?:\?|$)/,
    async (route) => {
      if (route.request().method() === "POST") return route.abort("blockedbyclient");
      return route.continue();
    },
  );
}
