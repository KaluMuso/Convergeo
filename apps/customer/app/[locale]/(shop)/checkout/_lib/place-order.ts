import { ApiError, createApiClient } from "@vergeo/config";

import type { ReviewPayment } from "../_components/step-review";

export type PlaceOrderGroup = {
  vendor_id: string;
  fulfilment: "delivery" | "pickup";
  delivery_zone: string | null;
  delivery_fee_ngwee: number;
  subtotal_ngwee: number;
};

export type PlaceOrderInput = {
  locale: string;
  accessToken: string;
  apiBaseUrl: string;
  sessionId: string;
  payment: ReviewPayment;
  groups: PlaceOrderGroup[];
  addressId?: string | null;
  idempotencyKey: string;
  navigate: (href: string) => void;
};

export type CreateOrderResponse = {
  checkout_group_id: string;
  idempotency_key: string;
  status: string;
  total_ngwee: number;
  replayed: boolean;
};

export type CardSessionResponse = {
  payment_id: string;
  checkout_group_id: string;
};

/**
 * Authoritative place-order: POST /orders then kick off MoMo/card or land on COD pending.
 * Does not invent totals — groups come from the fulfilment step response.
 */
export async function placeOrder(input: PlaceOrderInput): Promise<CreateOrderResponse> {
  const client = createApiClient({
    baseUrl: input.apiBaseUrl,
    getToken: () => input.accessToken,
  });

  const created = await client.request<CreateOrderResponse>("/orders", {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId,
      idempotency_key: input.idempotencyKey,
      method: input.payment.method,
      rail: input.payment.rail,
      payer_number: input.payment.payer_number,
      address_id: input.addressId ?? null,
      groups: input.groups,
    }),
  });

  const pendingHref = `/${input.locale}/checkout/pending/${encodeURIComponent(created.checkout_group_id)}`;

  if (input.payment.method === "cod") {
    input.navigate(pendingHref);
    return created;
  }

  if (input.payment.method === "card") {
    const card = await client.request<CardSessionResponse>("/payments/card/session", {
      method: "POST",
      body: JSON.stringify({ checkout_group_id: created.checkout_group_id }),
    });
    input.navigate(`/${input.locale}/checkout/card/${encodeURIComponent(card.payment_id)}`);
    return created;
  }

  // MoMo: first push via /payments/retry (creates payment when none exists).
  await client.request("/payments/retry", {
    method: "POST",
    body: JSON.stringify({
      checkout_group_id: created.checkout_group_id,
      payer_number: input.payment.payer_number,
      rail: input.payment.rail ?? "mtn",
    }),
  });
  input.navigate(pendingHref);
  return created;
}

export function placeOrderErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (typeof error.message === "string" && error.message.trim()) {
      return error.message;
    }
  }
  return fallback;
}
