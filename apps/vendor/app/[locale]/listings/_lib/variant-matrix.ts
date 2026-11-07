/**
 * Vendor-side variant editor model: option groups (Colour, Size) → the matrix
 * of purchasable combinations, each with SKU, stock, price override and photo.
 *
 * Money stays a ZMW decimal string while typing and becomes integer ngwee only
 * through `zmwDecimalToNgwee` (no float arithmetic). Mirrors the API rules in
 * services/api/app/services/listings/variants.py so most mistakes are caught
 * before a round-trip; the API remains the authority.
 */

import { zmwDecimalToNgwee } from "../new/_lib/money";

export const MAX_GROUPS = 3;
export const MAX_VALUES_PER_GROUP = 30;
export const MAX_VARIANTS = 100;
const SKU_RE = /^[A-Za-z0-9][A-Za-z0-9._\-/]{0,119}$/;
const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

export type GroupDisplay = "pill" | "swatch";

export type GroupDraft = {
  key: string;
  name: string;
  display: GroupDisplay;
  values: Array<{ key: string; label: string; swatchHex: string }>;
};

export type VariantRowDraft = {
  /** One value label per group, in group order. */
  options: string[];
  sku: string;
  stock: string;
  /** ZMW decimal; empty = use the listing price. */
  price: string;
  imagePublicId: string;
  active: boolean;
};

export type VariantsPayload = {
  groups: Array<{
    name: string;
    display: GroupDisplay;
    values: Array<{ label: string; swatch_hex?: string }>;
  }>;
  variants: Array<{
    options: string[];
    sku: string | null;
    stock_qty: number | null;
    price_ngwee: number | null;
    image_public_id: string | null;
    status: "active" | "archived";
  }>;
};

/** i18n reason keys under vendor.listings.variants.errors.* */
export type VariantErrorKey =
  | "groupNameRequired"
  | "duplicateGroup"
  | "valuesRequired"
  | "valueLabelRequired"
  | "duplicateValue"
  | "invalidSwatch"
  | "tooManyGroups"
  | "tooManyValues"
  | "tooManyVariants"
  | "variantsRequired"
  | "activeVariantRequired"
  | "invalidSku"
  | "duplicateSku"
  | "invalidStock"
  | "stockRequired"
  | "invalidPrice";

export type VariantErrors = Record<string, VariantErrorKey>;

function comboKey(options: string[]): string {
  return options.map((option) => option.trim().toLowerCase()).join("\u0000");
}

function cartesian(lists: string[][]): string[][] {
  return lists.reduce<string[][]>(
    (acc, list) => acc.flatMap((prefix) => list.map((item) => [...prefix, item])),
    [[]],
  );
}

/**
 * Rebuild the matrix after groups change. Rows for combinations that still
 * exist keep everything the vendor typed (matched case-insensitively), new
 * combinations start active and empty, and removed combinations are dropped.
 */
export function generateMatrix(groups: GroupDraft[], existing: VariantRowDraft[]): VariantRowDraft[] {
  const usable = groups
    .map((group) => group.values.map((value) => value.label.trim()).filter(Boolean))
    .filter((labels) => labels.length > 0);
  if (usable.length === 0 || usable.length !== groups.length) {
    return [];
  }
  const byKey = new Map(existing.map((row) => [comboKey(row.options), row]));
  return cartesian(usable).map((options) => {
    const previous = byKey.get(comboKey(options));
    return previous
      ? { ...previous, options }
      : { options, sku: "", stock: "", price: "", imagePublicId: "", active: true };
  });
}

export function validateDraft(
  groups: GroupDraft[],
  rows: VariantRowDraft[],
  options: { stockTracked: boolean },
): VariantErrors {
  const errors: VariantErrors = {};
  if (groups.length > MAX_GROUPS) {
    errors.groups = "tooManyGroups";
  }
  const names = new Set<string>();
  groups.forEach((group, gi) => {
    const name = group.name.trim();
    if (!name) {
      errors[`groups.${gi}.name`] = "groupNameRequired";
    } else if (names.has(name.toLowerCase())) {
      errors[`groups.${gi}.name`] = "duplicateGroup";
    }
    names.add(name.toLowerCase());
    if (group.values.length === 0) {
      errors[`groups.${gi}.values`] = "valuesRequired";
    }
    if (group.values.length > MAX_VALUES_PER_GROUP) {
      errors[`groups.${gi}.values`] = "tooManyValues";
    }
    const labels = new Set<string>();
    group.values.forEach((value, vi) => {
      const label = value.label.trim();
      if (!label) {
        errors[`groups.${gi}.values.${vi}`] = "valueLabelRequired";
      } else if (labels.has(label.toLowerCase())) {
        errors[`groups.${gi}.values.${vi}`] = "duplicateValue";
      } else if (group.display === "swatch" && value.swatchHex && !HEX_RE.test(value.swatchHex)) {
        errors[`groups.${gi}.values.${vi}`] = "invalidSwatch";
      }
      labels.add(label.toLowerCase());
    });
  });

  if (groups.length === 0) {
    return errors;
  }
  if (rows.length === 0) {
    errors.variants = "variantsRequired";
    return errors;
  }
  if (rows.length > MAX_VARIANTS) {
    errors.variants = "tooManyVariants";
  }
  if (!rows.some((row) => row.active)) {
    errors.variants = "activeVariantRequired";
  }
  const skus = new Set<string>();
  rows.forEach((row, index) => {
    const sku = row.sku.trim();
    if (sku) {
      if (!SKU_RE.test(sku)) {
        errors[`variants.${index}.sku`] = "invalidSku";
      } else if (skus.has(sku.toLowerCase())) {
        errors[`variants.${index}.sku`] = "duplicateSku";
      }
      skus.add(sku.toLowerCase());
    }
    const stock = row.stock.trim();
    if (stock && !/^\d{1,7}$/.test(stock)) {
      errors[`variants.${index}.stock`] = "invalidStock";
    } else if (!stock && options.stockTracked && row.active) {
      errors[`variants.${index}.stock`] = "stockRequired";
    }
    const price = row.price.trim();
    if (price) {
      try {
        if (zmwDecimalToNgwee(price) <= 0) {
          errors[`variants.${index}.price`] = "invalidPrice";
        }
      } catch {
        errors[`variants.${index}.price`] = "invalidPrice";
      }
    }
  });
  return errors;
}

/** Build the PUT body. Call only after `validateDraft` returned no errors. */
export function toPayload(groups: GroupDraft[], rows: VariantRowDraft[]): VariantsPayload {
  if (groups.length === 0) {
    return { groups: [], variants: [] };
  }
  return {
    groups: groups.map((group) => ({
      name: group.name.trim(),
      display: group.display,
      values: group.values.map((value) => ({
        label: value.label.trim(),
        ...(group.display === "swatch" && value.swatchHex ? { swatch_hex: value.swatchHex } : {}),
      })),
    })),
    variants: rows.map((row) => ({
      options: row.options,
      sku: row.sku.trim() || null,
      stock_qty: row.stock.trim() ? Number.parseInt(row.stock.trim(), 10) : null,
      price_ngwee: row.price.trim() ? zmwDecimalToNgwee(row.price.trim()) : null,
      image_public_id: row.imagePublicId || null,
      status: row.active ? "active" : "archived",
    })),
  };
}

let keyCounter = 0;
export function newKey(prefix: string): string {
  keyCounter += 1;
  return `${prefix}-${keyCounter}`;
}
