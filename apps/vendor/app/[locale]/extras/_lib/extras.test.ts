import { describe, expect, it } from "vitest";

import {
  extraPriceLabel,
  openRequestFor,
  type Extra,
  type ExtraRequest,
} from "./extras";

const t = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

const base: Extra = {
  key: "store_design",
  name: "Store design",
  description: "",
  pricing: "range",
  price_ngwee: 50000,
  price_max_ngwee: 500000,
  unit: "one_off",
  price_is_placeholder: false,
};

describe("extraPriceLabel", () => {
  it("formats a range in kwacha from integer ngwee", () => {
    expect(extraPriceLabel(base, t)).toBe(
      'price.range:{"min":"K500.00","max":"K5,000.00","unit":"unit.one_off"}',
    );
  });

  it("formats fixed, pay-as-you-go and missing prices", () => {
    expect(
      extraPriceLabel(
        {
          ...base,
          pricing: "fixed",
          price_ngwee: 7500,
          price_max_ngwee: null,
          unit: "per_month",
        },
        t,
      ),
    ).toBe('price.fixed:{"price":"K75.00","unit":"unit.per_month"}');
    expect(
      extraPriceLabel(
        {
          ...base,
          pricing: "pay_as_you_go",
          price_ngwee: 1000,
          price_max_ngwee: null,
        },
        t,
      ),
    ).toContain("price.paygFrom");
    expect(
      extraPriceLabel(
        {
          ...base,
          pricing: "pay_as_you_go",
          price_ngwee: null,
          price_max_ngwee: null,
        },
        t,
      ),
    ).toBe("price.payg");
    expect(
      extraPriceLabel(
        { ...base, pricing: "fixed", price_ngwee: null, price_max_ngwee: null },
        t,
      ),
    ).toBe("price.onRequest");
  });
});

describe("openRequestFor", () => {
  const request = (status: ExtraRequest["status"]): ExtraRequest => ({
    id: status,
    extra_key: "store_design",
    quantity: 1,
    note: null,
    status,
    quoted_price_ngwee: null,
    admin_note: null,
    created_at: null,
  });

  it("returns only an open request (requested/quoted/approved)", () => {
    expect(
      openRequestFor(
        [request("fulfilled"), request("cancelled")],
        "store_design",
      ),
    ).toBe(undefined);
    expect(
      openRequestFor([request("cancelled"), request("quoted")], "store_design")
        ?.id,
    ).toBe("quoted");
    expect(openRequestFor([request("requested")], "custom_domain")).toBe(
      undefined,
    );
  });
});
