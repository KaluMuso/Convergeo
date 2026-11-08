import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: async () => null }));

import { formatCtr, NEXT_STATUSES } from "../../advertising/_components/AdvertisingBoard";

import { moveItem, ngweeToKwachaInput, parseKwachaToNgwee, splitList } from "./feed-admin-api";
import { draftToBody } from "./HomeFeedBoard";

describe("money input (integer ngwee, no floats)", () => {
  it.each([
    ["100", 10_000],
    ["99.5", 9_950],
    ["99.50", 9_950],
    ["1,250.05", 125_005],
    ["K15", 1_500],
    ["0", 0],
  ])("parses %s", (input, expected) => {
    expect(parseKwachaToNgwee(input)).toBe(expected);
  });

  it.each(["", "abc", "1.234", "-5", "1e3", "12.3.4"])("rejects %s", (input) => {
    expect(parseKwachaToNgwee(input)).toBeNull();
  });

  it("round-trips ngwee to an editable string", () => {
    expect(ngweeToKwachaInput(10_000)).toBe("100");
    expect(ngweeToKwachaInput(9_950)).toBe("99.50");
    expect(ngweeToKwachaInput(null)).toBe("");
  });
});

describe("reorder + list helpers", () => {
  it("moves items within bounds only", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveItem(["a", "b", "c"], 2, 1)).toEqual(["a", "b", "c"]);
    expect(splitList("a, b\n c,,")).toEqual(["a", "b", "c"]);
  });
});

describe("draftToBody", () => {
  const base = {
    id: null,
    key: "cheap_finds",
    section_type: "rule" as const,
    layout: "grid",
    title_key: "",
    title_en: "Cheap finds",
    title_fr: "",
    limit: "12",
    category_path: "",
    listing_ids: "",
    rule_paths: "electronics, fashion",
    rule_price_max: "100",
    rule_sort: "cheapest",
    rule_keywords: "",
    rule_new_days: "",
    within_days: "",
    view_all_href: "",
    starts_at: "",
    ends_at: "",
    audience: "all",
    enabled: true,
  };

  it("builds a rule config with integer ngwee", () => {
    const result = draftToBody(base);
    expect("body" in result).toBe(true);
    if (!("body" in result)) return;
    expect(result.body.config).toMatchObject({
      rule: {
        category_paths: ["electronics", "fashion"],
        price_max_ngwee: 10_000,
        sort: "cheapest",
      },
    });
    expect(result.body.key).toBe("cheap_finds");
  });

  it("rejects an invalid price and forces the ad layout for ad slots", () => {
    expect(draftToBody({ ...base, rule_price_max: "ten" })).toEqual({ error: "invalidPrice" });
    const ad = draftToBody({ ...base, section_type: "ad_slot" });
    expect("body" in ad && ad.body.layout).toBe("ad");
  });

  it("clears the schedule on edit when both dates are blank", () => {
    const edit = draftToBody({ ...base, id: "x" });
    expect("body" in edit && edit.body.clear_schedule).toBe(true);
    expect("body" in edit && "key" in edit.body).toBe(false);
  });
});

describe("advertising helpers", () => {
  it("mirrors the guarded state machine", () => {
    expect(NEXT_STATUSES.draft).toEqual(["scheduled"]);
    expect(NEXT_STATUSES.ended).toEqual([]);
    expect(NEXT_STATUSES.active).not.toContain("draft");
  });

  it("formats CTR from basis points", () => {
    expect(formatCtr(123)).toBe("1.23%");
    expect(formatCtr(0)).toBe("0.00%");
  });
});
