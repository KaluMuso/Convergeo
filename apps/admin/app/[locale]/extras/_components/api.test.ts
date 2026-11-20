import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => null }));

import {
  adminActions,
  extraPayload,
  transitionBody,
  trialEndFromDate,
  type ExtraDraft,
} from "./api";

const draft = (patch: Partial<ExtraDraft>): ExtraDraft => ({
  name: "Store design",
  description: "",
  pricing: "fixed",
  price: "500",
  priceMax: "",
  unit: "one_off",
  active: true,
  ...patch,
});

describe("extras admin helpers", () => {
  it("mirrors the DB state machine's admin edges", () => {
    expect(adminActions("requested")).toEqual([
      "quoted",
      "approved",
      "cancelled",
    ]);
    expect(adminActions("quoted")).toEqual(["quoted", "approved", "cancelled"]);
    expect(adminActions("approved")).toEqual(["fulfilled", "cancelled"]);
    expect(adminActions("fulfilled")).toEqual([]);
    expect(adminActions("cancelled")).toEqual([]);
  });

  it("quotes in integer ngwee and refuses an invalid quote", () => {
    expect(transitionBody("quoted", "1,250.50", " ok ")).toEqual({
      to: "quoted",
      note: "ok",
      quoted_price_ngwee: 125050,
    });
    expect(transitionBody("quoted", "12.345", "")).toBeNull();
    expect(transitionBody("quoted", "", "")).toBeNull();
    expect(transitionBody("approved", "999", "")).toEqual({ to: "approved" });
  });

  it("validates the catalogue price shape before saving", () => {
    expect(extraPayload(draft({}))).toMatchObject({
      price_ngwee: 50000,
      price_max_ngwee: null,
    });
    expect(
      extraPayload(draft({ pricing: "range", price: "500", priceMax: "5000" })),
    ).toMatchObject({
      price_ngwee: 50000,
      price_max_ngwee: 500000,
    });
    expect(
      extraPayload(draft({ pricing: "range", price: "500", priceMax: "500" })),
    ).toBeNull();
    expect(
      extraPayload(draft({ pricing: "fixed", priceMax: "10" })),
    ).toBeNull();
    expect(
      extraPayload(draft({ pricing: "pay_as_you_go", price: "" })),
    ).toMatchObject({
      price_ngwee: null,
    });
    expect(extraPayload(draft({ price: "abc" }))).toBeNull();
    expect(extraPayload(draft({ name: "  " }))).toBeNull();
  });

  it("turns a picked date into the end of that day in Lusaka", () => {
    expect(trialEndFromDate("2027-03-01")).toBe("2027-03-01T23:59:59+02:00");
    expect(trialEndFromDate("")).toBeNull();
    expect(trialEndFromDate("01/03/2027")).toBeNull();
  });
});
