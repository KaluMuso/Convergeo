import { buildCategoryTree, type NavCategory } from "../_components/category-tree";

import type { CategoriesLoadResult } from "../_components/merch-data";

export type CategoriesBrowseView =
  | { kind: "populated"; tree: NavCategory[] }
  | { kind: "empty" }
  | { kind: "unavailable"; reason: Exclude<CategoriesLoadResult, { ok: true }>["reason"] };

/**
 * Map a load result to the browse UI state.
 * Empty success and operational failures stay distinguishable.
 */
export function resolveCategoriesBrowseView(result: CategoriesLoadResult): CategoriesBrowseView {
  if (!result.ok) {
    return { kind: "unavailable", reason: result.reason };
  }

  const tree = buildCategoryTree(
    result.categories.map((row) => ({
      id: row.id,
      name: row.name,
      slug: row.slug,
      position: row.position,
      parent_id: row.parent_id,
      prohibited: row.prohibited,
    })),
  );

  if (tree.length === 0) {
    return { kind: "empty" };
  }

  return { kind: "populated", tree };
}
