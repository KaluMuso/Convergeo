// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  CouponManager,
  kwachaToNgwee,
  percentToBps,
  type CouponManagerLabels,
} from "./coupon-manager";

const labels = new Proxy({ errors: { generic: "generic", amount: "bad amount" } } as never, {
  get: (target: Record<string, unknown>, key: string) => target[key] ?? key,
}) as CouponManagerLabels;

describe("coupon money parsing", () => {
  it("converts Kwacha to integer ngwee without floats", () => {
    expect(kwachaToNgwee("20")).toBe(2_000);
    expect(kwachaToNgwee("12.5")).toBe(1_250);
    expect(kwachaToNgwee("K1,234.56")).toBe(123_456);
    expect(kwachaToNgwee("0.1")).toBe(10);
    expect(kwachaToNgwee("1.234")).toBeNull();
    expect(kwachaToNgwee("-5")).toBeNull();
  });

  it("converts percent to basis points", () => {
    expect(percentToBps("10")).toBe(1_000);
    expect(percentToBps("12.5%")).toBe(1_250);
    expect(percentToBps("0")).toBeNull();
    expect(percentToBps("101")).toBeNull();
  });
});

describe("CouponManager", () => {
  it("sends integer ngwee and a vendor scope", async () => {
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") return { id: "c1" };
      void path;
      return { coupons: [] };
    });
    render(
      <CouponManager
        mode="vendor"
        locale="en"
        labels={labels}
        basePath="/vendor/coupons"
        request={request as never}
      />,
    );
    fireEvent.change(screen.getByLabelText("code", { exact: false }), {
      target: { value: "shop20" },
    });
    fireEvent.change(screen.getByLabelText("kind"), { target: { value: "fixed" } });
    fireEvent.change(screen.getByLabelText("amount", { exact: false }), {
      target: { value: "20.50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "create" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/vendor/coupons",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const post = request.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(String(post?.[1]?.body));
    expect(body).toMatchObject({
      code: "SHOP20",
      kind: "fixed",
      amount_ngwee: 2_050,
      percent_bps: null,
      scope: "vendor",
      scope_id: null,
      per_user_limit: 1,
    });
  });
});
