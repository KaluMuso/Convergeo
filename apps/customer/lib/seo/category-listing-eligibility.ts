/**
 * Pure rules: which category PLP paths have live catalogue content and how
 * category pages should be indexed.
 */

export type CategoryPathRow = {
  path: string;
  prohibited: boolean;
};

export type ListingPathStamp = {
  category_path: string;
  updated_at: string;
};

export type CategorySitemapRow = {
  path: string;
  lastModified?: Date;
};

/** Meta robots for category PLP — empty shelfs stay reachable but not indexed. */
export function categoryPlpRobots(
  hasFilters: boolean,
  listingTotal: number,
): { index: boolean; follow: boolean } {
  return {
    index: !hasFilters && listingTotal > 0,
    follow: true,
  };
}

function ancestorPaths(categoryPath: string): string[] {
  const parts = categoryPath.split("/").filter(Boolean);
  const paths: string[] = [];
  for (let depth = 1; depth <= parts.length; depth += 1) {
    paths.push(parts.slice(0, depth).join("/"));
  }
  return paths;
}

/**
 * Categories (and parents) that should appear in the sitemap: the category path
 * or any descendant path has at least one live listing projection.
 */
export function categoryPathsEligibleForSitemap(
  categories: readonly CategoryPathRow[],
  listingStamps: readonly ListingPathStamp[],
): CategorySitemapRow[] {
  const allowedPaths = new Set(
    categories.filter((row) => !row.prohibited && row.path.trim()).map((row) => row.path),
  );
  const lastModified = new Map<string, Date>();

  for (const stamp of listingStamps) {
    const categoryPath = stamp.category_path.trim();
    if (!categoryPath) {
      continue;
    }
    const updated = new Date(stamp.updated_at);
    if (Number.isNaN(updated.getTime())) {
      continue;
    }
    for (const path of ancestorPaths(categoryPath)) {
      if (!allowedPaths.has(path)) {
        continue;
      }
      const previous = lastModified.get(path);
      if (!previous || updated > previous) {
        lastModified.set(path, updated);
      }
    }
  }

  const eligible = [...allowedPaths].filter((path) => lastModified.has(path));
  eligible.sort((left, right) => left.localeCompare(right));

  return eligible.map((path) => ({
    path,
    ...(lastModified.has(path) ? { lastModified: lastModified.get(path) } : {}),
  }));
}
