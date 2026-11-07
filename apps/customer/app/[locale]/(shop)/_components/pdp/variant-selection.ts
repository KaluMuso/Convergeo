/**
 * Pure colour/size picker logic for the PDP (no React, unit-tested directly).
 *
 * A listing's variants are the purchasable combinations of its option groups
 * (e.g. Colour × Size). The buyer picks one value per group; a value is shown as
 *   - "available"   — some in-stock variant matches it plus the other picks,
 *   - "soldOut"     — a matching variant exists but has no stock,
 *   - "unavailable" — the vendor does not offer that combination at all.
 * Only "available" values can be chosen; the others stay visible but disabled.
 */

export type VariantOptionValue = {
  id: string;
  label: string;
  swatchHex: string | null;
};

export type VariantOptionGroup = {
  id: string;
  name: string;
  display: "pill" | "swatch";
  values: VariantOptionValue[];
};

export type ListingVariantOption = {
  id: string;
  sku: string | null;
  optionValueIds: string[];
  priceNgwee: number;
  compareAtNgwee: number | null;
  stockQty: number | null;
  inStock: boolean;
  imagePublicId: string | null;
};

/** groupId -> chosen valueId */
export type VariantSelection = Record<string, string>;

export type ValueAvailability = "available" | "soldOut" | "unavailable";

function matches(
  variant: ListingVariantOption,
  selection: VariantSelection,
  groups: VariantOptionGroup[],
): boolean {
  return groups.every((group) => {
    const chosen = selection[group.id];
    return chosen === undefined || variant.optionValueIds.includes(chosen);
  });
}

export function valueAvailability(
  groups: VariantOptionGroup[],
  variants: ListingVariantOption[],
  selection: VariantSelection,
  groupId: string,
  valueId: string,
): ValueAvailability {
  // Judge the value against the buyer's picks in the OTHER groups only, so a
  // buyer can always switch within a group.
  const probe: VariantSelection = { ...selection, [groupId]: valueId };
  const candidates = variants.filter((variant) => matches(variant, probe, groups));
  if (candidates.length === 0) {
    return "unavailable";
  }
  return candidates.some((variant) => variant.inStock) ? "available" : "soldOut";
}

export function resolveVariant(
  groups: VariantOptionGroup[],
  variants: ListingVariantOption[],
  selection: VariantSelection,
): ListingVariantOption | null {
  if (groups.length === 0 || groups.some((group) => selection[group.id] === undefined)) {
    return null;
  }
  return variants.find((variant) => matches(variant, selection, groups)) ?? null;
}

export function missingGroups(
  groups: VariantOptionGroup[],
  selection: VariantSelection,
): VariantOptionGroup[] {
  return groups.filter((group) => selection[group.id] === undefined);
}

/**
 * Apply a pick. Picks in other groups that no longer form an offered
 * combination with the new value are cleared rather than silently swapped.
 */
export function selectValue(
  groups: VariantOptionGroup[],
  variants: ListingVariantOption[],
  selection: VariantSelection,
  groupId: string,
  valueId: string,
): VariantSelection {
  const next: VariantSelection = { ...selection, [groupId]: valueId };
  for (const group of groups) {
    if (group.id === groupId || next[group.id] === undefined) {
      continue;
    }
    const stillOffered = variants.some((variant) =>
      matches(variant, { [groupId]: valueId, [group.id]: next[group.id] as string }, groups),
    );
    if (!stillOffered) {
      delete next[group.id];
    }
  }
  return next;
}

/** Preselect groups that offer exactly one in-stock value (e.g. a single colour). */
export function initialSelection(
  groups: VariantOptionGroup[],
  variants: ListingVariantOption[],
): VariantSelection {
  const selection: VariantSelection = {};
  for (const group of groups) {
    const offered = group.values.filter(
      (value) => valueAvailability(groups, variants, {}, group.id, value.id) === "available",
    );
    if (offered.length === 1 && group.values.length === 1 && offered[0]) {
      selection[group.id] = offered[0].id;
    }
  }
  return selection;
}

/** "Colour: Red · Size: M" style pairs for display. */
export function selectedOptionPairs(
  groups: VariantOptionGroup[],
  selection: VariantSelection,
): Array<{ group: string; value: string }> {
  const pairs: Array<{ group: string; value: string }> = [];
  for (const group of groups) {
    const value = group.values.find((candidate) => candidate.id === selection[group.id]);
    if (value) {
      pairs.push({ group: group.name, value: value.label });
    }
  }
  return pairs;
}

/** Join option pairs with a localized "{group}: {value}" template and separator. */
export function formatVariantLabel(
  pairs: Array<{ group: string; value: string }>,
  template: string,
  separator: string,
): string {
  return pairs
    .map((pair) => template.replaceAll("{group}", pair.group).replaceAll("{value}", pair.value))
    .join(separator);
}
