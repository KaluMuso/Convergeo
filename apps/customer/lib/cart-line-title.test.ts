import { describe, expect, it } from "vitest";
import { cartLineTitle } from "./cart-line-title";

const LISTING_ID = "1633639e-0000-4000-8000-000000000001";

describe("cartLineTitle", () => {
  it("uses the resolved title", () => {
    expect(cartLineTitle({ title_override: " Blue Kettle " }, "Item")).toBe("Blue Kettle");
  });

  it("falls back to the translated label, never the listing id", () => {
    const item = { title_override: null, listing_id: LISTING_ID };
    expect(cartLineTitle(item, "Item")).toBe("Item");
    expect(cartLineTitle(item)).not.toContain(LISTING_ID);
    expect(cartLineTitle({ title_override: "  " }, "Item")).toBe("Item");
  });
});
