/**
 * Default category imagery for top-level departments.
 *
 * Merch payloads (`category_grid.images`) always win; these defaults keep the
 * home category rail photographic when no campaign art is configured. They
 * point at the seeded Cloudinary `demo/categories/*` set (real product
 * photography, no people, no brand marks).
 *
 * TODO(design): swap to `vergeo5/categories/<slug>` once the commissioned /
 * generated set is uploaded — Cloudinary generation was unavailable when this
 * shipped (token lacked the media_generation scope).
 */
export const DEFAULT_CATEGORY_IMAGES: Readonly<Record<string, string>> = {
  "groceries-staples": "demo/categories/rice-grains",
  "personal-care-beauty": "demo/categories/skincare",
  fashion: "demo/categories/chitenge-fabric",
  electronics: "demo/categories/mobile-phones",
  "home-living": "demo/categories/home-decor",
  "office-stationery": "demo/categories/paper-notebooks",
  "light-hardware": "demo/categories/hand-tools",
};

export function defaultCategoryImage(slug: string): string | undefined {
  return Object.prototype.hasOwnProperty.call(DEFAULT_CATEGORY_IMAGES, slug)
    ? DEFAULT_CATEGORY_IMAGES[slug]
    : undefined;
}
