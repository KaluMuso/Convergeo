import { describe, expect, it } from "vitest";

import { EMPTY_FORM, kwachaToNgwee, toRequestBody } from "./import-requests";

describe("kwachaToNgwee", () => {
  it("converts without floating point", () => {
    expect(kwachaToNgwee("35")).toBe(3500);
    expect(kwachaToNgwee("35.5")).toBe(3550);
    expect(kwachaToNgwee("0.07")).toBe(7);
    expect(kwachaToNgwee("1.005")).toBeNull();
    expect(kwachaToNgwee("-1")).toBeNull();
    expect(kwachaToNgwee("abc")).toBeNull();
  });
});

describe("toRequestBody", () => {
  const valid = {
    ...EMPTY_FORM,
    title: "LED strips",
    quantity: "200",
    targetPrice: "35.50",
  };

  it("builds an integer-ngwee body and drops blanks", () => {
    expect(toRequestBody(valid)).toEqual({
      title: "LED strips",
      quantity: 200,
      unit: "pcs",
      image_urls: [],
      target_unit_price_ngwee: 3550,
    });
  });

  it("splits photo links by line", () => {
    const body = toRequestBody({
      ...valid,
      imageUrls: "https://a.com/1.jpg\n\n https://a.com/2.jpg ",
    });
    expect(body?.image_urls).toEqual(["https://a.com/1.jpg", "https://a.com/2.jpg"]);
  });

  it("rejects bad quantity, short title and bad price", () => {
    expect(toRequestBody({ ...valid, quantity: "0" })).toBeNull();
    expect(toRequestBody({ ...valid, quantity: "1.5" })).toBeNull();
    expect(toRequestBody({ ...valid, title: "ab" })).toBeNull();
    expect(toRequestBody({ ...valid, targetPrice: "0" })).toBeNull();
    expect(toRequestBody({ ...valid, targetPrice: "x" })).toBeNull();
  });
});
