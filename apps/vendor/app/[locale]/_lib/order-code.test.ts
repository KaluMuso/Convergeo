import { describe, expect, it } from "vitest";

import {
  formatOrderCode,
  hasApprovedLiveListing,
  isFullOrderUuid,
  resolveOrderIdFromInput,
} from "./order-code";

const FULL = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

describe("formatOrderCode", () => {
  it("returns 8 uppercase chars without hyphens", () => {
    expect(formatOrderCode(FULL)).toBe("AAAAAAAA");
    expect(formatOrderCode("abcdef01-2345-6789-abcd-ef0123456789")).toBe("ABCDEF01");
  });
});

describe("resolveOrderIdFromInput", () => {
  const candidates = [{ id: FULL }, { id: OTHER }];

  it("accepts a full UUID", () => {
    expect(resolveOrderIdFromInput(FULL, candidates)).toBe(FULL);
  });

  it("accepts an 8-character short code", () => {
    expect(resolveOrderIdFromInput("AAAAAAAA", candidates)).toBe(FULL);
    expect(resolveOrderIdFromInput("aaaaaaa", candidates)).toBe(null);
  });

  it("returns null when the prefix matches more than one order", () => {
    const ambiguous = [
      { id: "aaaaaaaa-0001-4000-8000-000000000001" },
      { id: "aaaaaaaa-0002-4000-8000-000000000002" },
    ];
    expect(resolveOrderIdFromInput("AAAAAAAA", ambiguous)).toBe(null);
  });
});

describe("isFullOrderUuid", () => {
  it("detects canonical UUIDs", () => {
    expect(isFullOrderUuid(FULL)).toBe(true);
    expect(isFullOrderUuid("not-a-uuid")).toBe(false);
  });
});

describe("hasApprovedLiveListing", () => {
  it("requires active listing with product approved for buyers", () => {
    expect(
      hasApprovedLiveListing([
        { status: "draft", product_status: "approved" },
        { status: "active", product_status: "pending_moderation" },
        { status: "active", product_status: null },
      ]),
    ).toBe(true);
    expect(
      hasApprovedLiveListing([{ status: "active", product_status: "pending_moderation" }]),
    ).toBe(false);
  });
});
