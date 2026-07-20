import type { Page, Route } from "@playwright/test";

import { BASE_URL, flag, lencoSandboxReady, str } from "./env";

/**
 * Deterministic payment-status / card-verify fixtures for CI (provider-mock mode).
 *
 * Deployed-target mode leaves these unused and exercises the live sandbox stack
 * when `LENCO_SANDBOX` + creds are present (F9b). Secrets never appear in
 * assertions — only status enums and public UI copy.
 */

export type PaymentStatusFixture = {
  checkout_group_id: string;
  payment_id: string | null;
  status: string;
  amount_ngwee: number;
  rail: string | null;
  cod: boolean;
  order_id: string;
  payer_phone: string | null;
};

export type CardVerifyFixture = {
  payment_id: string;
  checkout_group_id: string;
  status: string;
  verified: boolean;
  order_confirmed: boolean;
  held?: boolean;
  retry_checkout?: boolean;
};

export const FIXTURE_GROUP_ID = "e2e00000-0000-4000-8000-000000000001";
export const FIXTURE_PAYMENT_ID = "e2e00000-0000-4000-8000-0000000000p1";
export const FIXTURE_ORDER_ID = "e2e00000-0000-4000-8000-0000000000o1";

/** True when the suite should prefer route-mocked payment APIs (default in CI). */
export function paymentMockMode(): boolean {
  if (flag("E2E_PAYMENT_MOCK")) return true;
  if (flag("E2E_DEPLOYED_TARGET") || lencoSandboxReady()) return false;
  // Credential-free CI / local: mock by default so honesty specs stay deterministic.
  return true;
}

export function deployedTargetReady(): boolean {
  return flag("E2E_DEPLOYED_TARGET") || (str("E2E_BASE_URL").length > 0 && !paymentMockMode());
}

/**
 * Refuse accidental real-money runs. Sandbox pay requires LENCO_SANDBOX; a live
 * Lenco env flag must never be paired with this suite's pay legs.
 */
export function assertNoAccidentalRealMoney(): void {
  const lencoEnv = str("LENCO_ENV").toLowerCase();
  if (lencoEnv === "live" || lencoEnv === "production") {
    throw new Error(
      `Refusing E2E pay against LENCO_ENV=${lencoEnv}. Use sandbox credentials only.`,
    );
  }
  if (flag("LENCO_LIVE") || flag("LENCO_PRODUCTION")) {
    throw new Error("Refusing E2E pay when LENCO_LIVE/LENCO_PRODUCTION is set.");
  }
  const base = BASE_URL.toLowerCase();
  if (
    (base.includes("api.lenco.co") || base.includes("pay.lenco.co")) &&
    !base.includes("sandbox")
  ) {
    throw new Error(`Refusing E2E against non-sandbox Lenco host: ${BASE_URL}`);
  }
}

const MOCK_SESSION = {
  access_token: "e2e-mock-access-token",
  refresh_token: "e2e-mock-refresh-token",
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  token_type: "bearer",
  user: {
    id: "e2e00000-0000-4000-8000-0000000000u1",
    aud: "authenticated",
    role: "authenticated",
    email: "e2e-buyer@example.com",
    phone: "+260970000001",
    app_metadata: { provider: "phone" },
    user_metadata: {},
    created_at: new Date().toISOString(),
  },
};

/**
 * Install a buyer session the customer app's Supabase client will accept locally
 * without contacting a real Auth project. Paired with `page.route` mocks for
 * GoTrue so refresh cannot clear the fixture.
 */
export async function installMockBuyerSession(page: Page): Promise<void> {
  await page.addInitScript((session) => {
    // Consumed by useSession when NEXT_PUBLIC_E2E_MOCK_SESSION=1.
    (window as unknown as { __VERGEO_E2E_SESSION__?: typeof session }).__VERGEO_E2E_SESSION__ =
      session;
    const raw = JSON.stringify(session);
    const proto = Storage.prototype;
    const originalGet = proto.getItem;
    proto.getItem = function patchedGetItem(key: string) {
      if (typeof key === "string" && (key.includes("auth-token") || key.includes("supabase"))) {
        return raw;
      }
      return originalGet.call(this, key);
    };
    try {
      window.localStorage.setItem("sb-e2e-auth-token", raw);
    } catch {
      /* private mode */
    }
  }, MOCK_SESSION);

  await page.route("**/auth/v1/**", async (route: Route) => {
    const url = route.request().url();
    if (url.includes("/logout")) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: MOCK_SESSION.access_token,
        refresh_token: MOCK_SESSION.refresh_token,
        expires_in: MOCK_SESSION.expires_in,
        expires_at: MOCK_SESSION.expires_at,
        token_type: "bearer",
        user: MOCK_SESSION.user,
      }),
    });
  });
}

export function statusFixture(overrides: Partial<PaymentStatusFixture> = {}): PaymentStatusFixture {
  return {
    checkout_group_id: FIXTURE_GROUP_ID,
    payment_id: FIXTURE_PAYMENT_ID,
    status: "ussd_pushed",
    amount_ngwee: 25_000,
    rail: "mtn",
    cod: false,
    order_id: FIXTURE_ORDER_ID,
    payer_phone: "+260970000001",
    ...overrides,
  };
}

export function cardVerifyFixture(overrides: Partial<CardVerifyFixture> = {}): CardVerifyFixture {
  return {
    payment_id: FIXTURE_PAYMENT_ID,
    checkout_group_id: FIXTURE_GROUP_ID,
    status: "success",
    verified: false,
    order_confirmed: false,
    ...overrides,
  };
}

type StatusResolver = PaymentStatusFixture | (() => PaymentStatusFixture);

/**
 * Intercept `GET /payments/status` (group or payment query). Resolver may be a
 * function so refresh / retry scenarios can advance state without sleeps.
 */
export async function mockPaymentStatus(
  page: Page,
  resolver: StatusResolver,
): Promise<{ calls: number[] }> {
  const tracker = { calls: [] as number[] };
  await page.route("**/payments/status**", async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    tracker.calls.push(Date.now());
    const payload = typeof resolver === "function" ? resolver() : resolver;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  return tracker;
}

export async function mockPaymentRetry(
  page: Page,
  result: { payment_id: string; status: string; order_count: number },
): Promise<{ calls: number }> {
  const state = { calls: 0 };
  await page.route("**/payments/retry", async (route: Route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    state.calls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        checkout_group_id: FIXTURE_GROUP_ID,
        payment_id: result.payment_id,
        status: result.status,
        order_count: result.order_count,
      }),
    });
  });
  return state;
}

export async function mockCardVerify(
  page: Page,
  resolver: CardVerifyFixture | (() => CardVerifyFixture),
): Promise<{ calls: number }> {
  const state = { calls: 0 };
  await page.route("**/payments/card/*/verify", async (route: Route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    state.calls += 1;
    const payload = typeof resolver === "function" ? resolver() : resolver;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  return state;
}

/** Copy that must never appear for pending/failed/unknown MoMo collections. */
export const FORBIDDEN_SUCCESS_COPY =
  /order confirmed|payment (is )?held by vergeo5|you paid|paid upfront|payment successful|successfully paid/i;
