import { describe, expect, it } from "vitest";

import { generateMatrix, toPayload, validateDraft, type GroupDraft } from "./variant-matrix";

function group(
  name: string,
  labels: string[],
  display: GroupDraft["display"] = "pill",
): GroupDraft {
  return {
    key: name,
    name,
    display,
    values: labels.map((label) => ({ key: `${name}-${label}`, label, swatchHex: "" })),
  };
}

const colour = group("Colour", ["Red", "Blue"], "swatch");
const size = group("Size", ["S", "M", "L"]);

describe("generateMatrix", () => {
  it("builds every combination in group order", () => {
    const rows = generateMatrix([colour, size], []);
    expect(rows.map((row) => row.options.join("/"))).toEqual([
      "Red/S",
      "Red/M",
      "Red/L",
      "Blue/S",
      "Blue/M",
      "Blue/L",
    ]);
    expect(rows.every((row) => row.active)).toBe(true);
  });

  it("keeps what the vendor typed when choices are added or renamed in case only", () => {
    const first = generateMatrix([colour, size], []).map((row, index) =>
      index === 0 ? { ...row, sku: "R-S", stock: "4", price: "250.00" } : row,
    );
    const renamed = {
      ...colour,
      values: [
        ...colour.values.map((v) => ({ ...v, label: v.label.toLowerCase() })),
        { key: "g", label: "Green", swatchHex: "" },
      ],
    };
    const next = generateMatrix([renamed, size], first);
    expect(next).toHaveLength(9);
    expect(next[0]).toMatchObject({
      options: ["red", "S"],
      sku: "R-S",
      stock: "4",
      price: "250.00",
    });
  });

  it("produces no rows while a group has no choices", () => {
    expect(generateMatrix([colour, group("Size", [])], [])).toEqual([]);
    expect(generateMatrix([], [])).toEqual([]);
  });
});

describe("validateDraft", () => {
  const rows = generateMatrix([colour, size], []).map((row) => ({ ...row, stock: "2" }));

  it("accepts a complete matrix", () => {
    expect(validateDraft([colour, size], rows, { stockTracked: true })).toEqual({});
  });

  it("requires stock for offered rows on tracked listings only", () => {
    const missing = rows.map((row, index) => (index === 1 ? { ...row, stock: "" } : row));
    expect(validateDraft([colour, size], missing, { stockTracked: true })).toEqual({
      "variants.1.stock": "stockRequired",
    });
    expect(validateDraft([colour, size], missing, { stockTracked: false })).toEqual({});
  });

  it("flags bad price, SKU, duplicates and empty names", () => {
    const bad = rows.map((row, index) =>
      index === 0
        ? { ...row, price: "12.345", sku: "A 1" }
        : index === 1
          ? { ...row, sku: "x" }
          : index === 2
            ? { ...row, sku: "X" }
            : row,
    );
    const errors = validateDraft([colour, size, group("", ["a"])], bad, { stockTracked: true });
    expect(errors["variants.0.price"]).toBe("invalidPrice");
    expect(errors["variants.0.sku"]).toBe("invalidSku");
    expect(errors["variants.2.sku"]).toBe("duplicateSku");
    expect(errors["groups.2.name"]).toBe("groupNameRequired");
    const dupGroups = validateDraft([colour, { ...colour, key: "c2", name: "colour" }], [], {
      stockTracked: false,
    });
    expect(dupGroups["groups.1.name"]).toBe("duplicateGroup");
  });

  it("requires at least one offered combination", () => {
    const none = rows.map((row) => ({ ...row, active: false }));
    expect(validateDraft([colour, size], none, { stockTracked: true }).variants).toBe(
      "activeVariantRequired",
    );
  });
});

describe("toPayload", () => {
  it("converts kwacha to integer ngwee and blanks to null", () => {
    const rows = generateMatrix([colour], []).map((row, index) =>
      index === 0
        ? { ...row, price: "1,250.5", stock: "3", sku: " R ", imagePublicId: "img/1" }
        : { ...row, active: false },
    );
    const payload = toPayload(
      [{ ...colour, values: [{ ...colour.values[0]!, swatchHex: "#C0392B" }, colour.values[1]!] }],
      rows,
    );
    expect(payload.groups[0]).toEqual({
      name: "Colour",
      display: "swatch",
      values: [{ label: "Red", swatch_hex: "#C0392B" }, { label: "Blue" }],
    });
    expect(payload.variants[0]).toEqual({
      options: ["Red"],
      sku: "R",
      stock_qty: 3,
      price_ngwee: 125_050,
      image_public_id: "img/1",
      status: "active",
    });
    expect(Number.isInteger(payload.variants[0]?.price_ngwee)).toBe(true);
    expect(payload.variants[1]).toMatchObject({
      price_ngwee: null,
      stock_qty: null,
      status: "archived",
    });
  });

  it("clears all variants when no groups remain", () => {
    expect(toPayload([], [])).toEqual({ groups: [], variants: [] });
  });
});
