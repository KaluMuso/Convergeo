import { FIXTURE_GROUP_ID, FIXTURE_ORDER_ID } from "./payment-fixtures";

import type { Page, Route } from "@playwright/test";

/**
 * Deterministic Checkout API for the customer wizard (mock mode, no backend).
 *
 * `/checkout` is client-driven: the server renders only the shell and every
 * datum arrives through the browser's own API calls, which `page.route` can
 * answer. Pair with `installMockBuyerSession` (the session carries a phone, so
 * the shell skips Contact and starts at Fulfilment).
 *
 * The contract mirrored here is the one the wizard types declare
 * (step-fulfilment.tsx `CheckoutSession`, step-payment.tsx `PaymentOptions`,
 * _lib/place-order.ts `CreateOrderResponse`). It is a UI-contract double, not a
 * claim about the backend's COD verdict — that verdict is covered by the API
 * test-suite; here we prove the UI renders and honours it.
 */

export const MOCK_VENDOR_ID = "e2e00000-0000-4000-8000-0000000000v1";
/** K500 COD cap, in ngwee (CLAUDE.md Zambia guardrails). */
export const COD_CAP_NGWEE = 50_000;

export type MockCheckoutOptions = {
  /** Cart subtotal. At or under COD_CAP_NGWEE => COD eligible. */
  subtotalNgwee: number;
  deliveryFeeNgwee?: number;
  /** Override the verdict; default derives from total vs cap. */
  codEligible?: boolean;
  itemTitle?: string;
};

export type MockCheckoutCalls = {
  orders: Array<Record<string, unknown>>;
  paymentSteps: Array<Record<string, unknown>>;
};

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function errorEnvelope(code: string, message: string) {
  return { error: { code, message, request_id: "e2e-req", details: {} } };
}

/**
 * `POST /cart/merge` runs on every signed-in transition (customer-session.ts).
 * Unanswered, the app shows a blocking "could not secure your cart" dialog, so
 * every mock-session spec answers it.
 */
export async function mockCartMerge(page: Page): Promise<void> {
  await page.route("**/cart/merge", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ status: 204, body: "" });
  });
}

export async function installMockCheckoutApi(
  page: Page,
  options: MockCheckoutOptions,
): Promise<MockCheckoutCalls> {
  const calls: MockCheckoutCalls = { orders: [], paymentSteps: [] };
  const delivery = options.deliveryFeeNgwee ?? 0;
  const total = options.subtotalNgwee + delivery;
  const codEligible = options.codEligible ?? total <= COD_CAP_NGWEE;
  const title = options.itemTitle ?? "E2E mock product";

  await mockCartMerge(page);

  await page.route("**/checkout/steps/contact", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await json(route, { verified: true });
  });

  await page.route("**/checkout/session", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await json(route, {
      session_id: FIXTURE_GROUP_ID,
      expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      reservation_ttl_min: 15,
      subtotal_ngwee: options.subtotalNgwee,
      contact_skipped: true,
      vendor_groups: [
        {
          vendor_id: MOCK_VENDOR_ID,
          vendor_name: "E2E mock vendor",
          subtotal_ngwee: options.subtotalNgwee,
          delivery_eligible: true,
          pickup_location: { landmark: "E2E pickup point", lat: -15.4, lng: 28.3, hours: {} },
          items: [
            {
              id: "e2e00000-0000-4000-8000-0000000000i1",
              listing_id: "e2e00000-0000-4000-8000-0000000000l1",
              vendor_id: MOCK_VENDOR_ID,
              qty: 1,
              unit_price_ngwee: options.subtotalNgwee,
              line_total_ngwee: options.subtotalNgwee,
              title_override: title,
            },
          ],
        },
      ],
    });
  });

  await page.route("**/account/addresses", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await json(route, { id: "e2e00000-0000-4000-8000-0000000000a1" }, 201);
  });

  await page.route("**/checkout/steps/fulfilment", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON() as {
      groups?: Array<{ vendor_id: string; fulfilment: "delivery" | "pickup" }>;
    };
    const groups = (body.groups ?? []).map((group) => ({
      vendor_id: group.vendor_id,
      fulfilment: group.fulfilment,
      delivery_zone: group.fulfilment === "delivery" ? "lusaka" : null,
      delivery_fee_ngwee: group.fulfilment === "delivery" ? delivery : 0,
      subtotal_ngwee: options.subtotalNgwee,
    }));
    const fee = groups.reduce((sum, group) => sum + group.delivery_fee_ngwee, 0);
    await json(route, {
      subtotal_ngwee: options.subtotalNgwee,
      delivery_fee_ngwee: fee,
      total_ngwee: options.subtotalNgwee + fee,
      groups,
    });
  });

  const paymentOptions = () => ({
    session_id: FIXTURE_GROUP_ID,
    subtotal_ngwee: options.subtotalNgwee,
    delivery_fee_ngwee: delivery,
    total_ngwee: total,
    cod_cap_ngwee: COD_CAP_NGWEE,
    cod_eligible: codEligible,
    available_methods: ["momo", "card", ...(codEligible ? ["cod"] : [])],
  });

  await page.route("**/checkout/steps/payment-options**", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await json(route, paymentOptions());
  });

  await page.route("**/checkout/steps/payment", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON() as Record<string, unknown>;
    calls.paymentSteps.push(body);
    if (body.method === "cod" && !codEligible) {
      await json(
        route,
        errorEnvelope("checkout.cod_ineligible", "COD not available for this total"),
        422,
      );
      return;
    }
    await json(route, {
      ...paymentOptions(),
      method: body.method,
      rail: body.rail ?? null,
      payer_number: body.payer_number ?? null,
    });
  });

  // POST /orders only — never the document route /{locale}/account/orders.
  await page.route(
    (url) => url.pathname === "/orders" || /^\/(?:v\d+\/)?orders$/.test(url.pathname),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      calls.orders.push(route.request().postDataJSON() as Record<string, unknown>);
      await json(
        route,
        {
          checkout_group_id: FIXTURE_GROUP_ID,
          idempotency_key: "e2e-key",
          status: "pending",
          total_ngwee: total,
          replayed: false,
        },
        201,
      );
    },
  );

  return calls;
}

export { FIXTURE_ORDER_ID };
