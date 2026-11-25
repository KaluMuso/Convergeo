import { describe, expect, it } from "vitest";

import { toPayload, type GroupDraft, type VariantRowDraft } from "./variant-matrix";

describe("toPayload money serialization", () => {
  it("sends integer ngwee, not decimal strings", () => {
    const groups: GroupDraft[] = [
      {
        key: "g1",
        name: "Colour",
        display: "pill",
        values: [{ key: "v1", label: "Red", swatchHex: "" }],
      },
    ];
    const rows: VariantRowDraft[] = [
      {
        options: ["Red"],
        sku: "",
        stock: "4",
        price: "250.50",
        imagePublicId: "",
        active: true,
      },
    ];
    const payload = toPayload(groups, rows);
    expect(payload.variants[0]?.price_ngwee).toBe(25_050);
    expect(payload.variants[0]?.stock_qty).toBe(4);
  });
});
