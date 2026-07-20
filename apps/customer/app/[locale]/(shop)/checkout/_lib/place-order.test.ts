import { ApiError } from "@vergeo/config";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { placeOrder, placeOrderErrorMessage } from "./place-order";

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

  it("surfaces ApiError messages", () => {
    expect(
      placeOrderErrorMessage(
        new ApiError("x", "Delivery address required", { status: 422 }),
        "fallback",
      ),
    ).toBe("Delivery address required");
    expect(placeOrderErrorMessage(new Error("nope"), "fallback")).toBe("fallback");
  });
});
