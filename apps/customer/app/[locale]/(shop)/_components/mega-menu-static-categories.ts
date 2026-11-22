import { MEGA_MENU_FALLBACK_ROOT_SLUGS } from "./mega-menu-fallback-slugs";

import type { NavCategory } from "./category-tree";

function titleFromSlug(slug: string): string {
  return slug
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Slug-stable top-level browse roots when the live catalogue cannot load. */
export function staticMegaMenuRootSlugs(): string[] {
  return [...MEGA_MENU_FALLBACK_ROOT_SLUGS];
}

/**
 * Build a shallow mega-menu tree from translated root labels (no grandchildren).
 * IDs are synthetic; slugs match the seeded department keys.
 */
export function buildStaticMegaMenuRoots(labelsBySlug: Record<string, string>): NavCategory[] {
  return staticMegaMenuRootSlugs().map((slug) => ({
    id: `static:${slug}`,
    name: labelsBySlug[slug] ?? titleFromSlug(slug),
    slug,
    children: [],
  }));
}
