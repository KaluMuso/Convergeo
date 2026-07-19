/**
 * Shared (server + client) category-tree helpers.
 *
 * Kept free of `"use client"` so Server Components can call `buildCategoryTree`
 * without crossing the Next.js client-module boundary (production digest
 * 3012388270).
 */

export type NavCategory = {
  id: string;
  name: string;
  slug: string;
  children: Array<{ id: string; name: string; slug: string }>;
};

export type CategoryRecord = {
  id: string;
  name: string;
  slug: string;
  position: number;
  parent_id: string | null;
  prohibited: boolean;
};

function byPosition(left: { position: number }, right: { position: number }): number {
  return left.position - right.position;
}

function isUsableRecord(row: CategoryRecord): boolean {
  return (
    typeof row.id === "string" &&
    row.id.length > 0 &&
    typeof row.name === "string" &&
    row.name.length > 0 &&
    typeof row.slug === "string" &&
    row.slug.length > 0 &&
    typeof row.position === "number" &&
    Number.isFinite(row.position) &&
    (row.parent_id === null || typeof row.parent_id === "string") &&
    typeof row.prohibited === "boolean" &&
    !row.prohibited
  );
}

/**
 * Group a flat category list into top-level entries with their children.
 * - Drops prohibited / incomplete rows.
 * - Orphans (parent_id not in the usable set) are not promoted to roots.
 * - Only one child level is materialised (Phase-1 browse depth).
 */
export function buildCategoryTree(rows: CategoryRecord[]): NavCategory[] {
  const usable = rows.filter(isUsableRecord);
  const byId = new Map(usable.map((row) => [row.id, row]));

  return usable
    .filter((row) => row.parent_id === null)
    .sort(byPosition)
    .map((top) => ({
      id: top.id,
      name: top.name,
      slug: top.slug,
      children: usable
        .filter((row) => row.parent_id === top.id && byId.has(top.id))
        .sort(byPosition)
        .map((child) => ({ id: child.id, name: child.name, slug: child.slug })),
    }));
}

/** True when every provided row fails structural validation (not merely empty). */
export function isMalformedCategoryPayload(rows: unknown): boolean {
  if (!Array.isArray(rows) || rows.length === 0) {
    return false;
  }
  return !rows.some((entry) => {
    if (!entry || typeof entry !== "object") {
      return false;
    }
    const row = entry as Partial<CategoryRecord>;
    return (
      typeof row.id === "string" &&
      typeof row.name === "string" &&
      typeof row.slug === "string" &&
      typeof row.position === "number" &&
      (row.parent_id === null || typeof row.parent_id === "string") &&
      typeof row.prohibited === "boolean"
    );
  });
}
