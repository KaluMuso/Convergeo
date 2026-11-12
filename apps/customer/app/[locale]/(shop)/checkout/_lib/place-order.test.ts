import { ApiError } from "@vergeo/config";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { classifyPlaceOrderError, placeOrder } from "./place-order";

const request = vi.fn();

vi.mock("@vergeo/config", async () => {
  const actual = await vi.importActual<typeof import("@vergeo/config")>("@vergeo/config");
  return {
    ...actual,
    createApiClient: () => ({ request }),
  };
});

describe("placeOrder", () => {
  beforeEach(() => {
    request.mockReset();
  });

  it("creates order then retries MoMo push", async () => {
    const navigate = vi.fn();
    request
      .mockResolvedValueOnce({
        checkout_group_id: "grp-1",
        idempotency_key: "idem-1",
        status: "pending_payment",
        total_ngwee: 10_000,
        replayed: false,
      })
      .mockResolvedValueOnce({ ok: true });

    await placeOrder({
      locale: "en",
      accessToken: "tok",
      apiBaseUrl: "https://api.example",
      sessionId: "sess-1",
      payment: { method: "momo", rail: "mtn", payer_number: "+260971234567" },
      groups: [
        {
          vendor_id: "v1",
          fulfilment: "delivery",
          delivery_zone: "lusaka_central",
          delivery_fee_ngwee: 0,
          subtotal_ngwee: 10_000,
        },
      ],
      addressId: "addr-1",
      idempotencyKey: "idem-1",
      navigate,
    });

    expect(request).toHaveBeenNthCalledWith(
      1,
      "/orders",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("addr-1"),
      }),
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/payments/retry",
      expect.objectContaining({ method: "POST" }),
    );
    expect(navigate).toHaveBeenCalledWith("/en/checkout/pending/grp-1");
  });
});

describe("classifyPlaceOrderError", () => {
  it("sends the buyer back to the cart when the stock hold lapsed", () => {
    expect(
      classifyPlaceOrderError(
        new ApiError("checkout.reservation_expired", "Your reservation has expired", {
          status: 410,
        }),
      ),
    ).toEqual({ kind: "return_to_cart", notice: "reservation_expired" });
  });

  it.each([
    "checkout.cart_changed",
    "checkout.stock_unavailable",
    "orders.totals_mismatch",
    "cart.variant_out_of_stock",
    "cart.variant_unavailable",
  ])("sends the buyer back to review a stale cart on %s", (code) => {
    expect(classifyPlaceOrderError(new ApiError(code, "server detail", { status: 409 }))).toEqual({
      kind: "return_to_cart",
      notice: "stock_unavailable",
    });
  });

  it("flags a cash-on-delivery rejection so the payment copy can explain it", () => {
    expect(
      classifyPlaceOrderError(
        new ApiError("checkout.cod_ineligible", "Cash on delivery is not available", {
          status: 422,
        }),
      ),
    ).toEqual({ kind: "cod_ineligible" });
  });

  it("never passes the API's developer English through", () => {
    expect(
      classifyPlaceOrderError(
        new ApiError("first_order_cap_exceeded", "Vendor cap enforcement blocked this action", {
          status: 403,
        }),
      ),
    ).toEqual({ kind: "unavailable" });
    expect(classifyPlaceOrderError(new Error("nope"))).toEqual({ kind: "unavailable" });
  });
});
