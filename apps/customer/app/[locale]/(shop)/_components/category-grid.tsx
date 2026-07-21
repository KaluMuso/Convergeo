import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import Link from "next/link";

import type { CategoryRow, MerchSlotRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

const CATEGORY_PASTELS = [
  "var(--cat-beauty)",
  "var(--cat-health)",
  "var(--cat-food)",
  "var(--cat-fitness)",
  "var(--cat-home)",
  "var(--cat-auto)",
] as const;

/** Lightweight geometric marks — no emoji, no extra icon pack. */
const CATEGORY_ICON_PATHS = [
  "M4 8h16v10H4zM8 8V6h8v2",
  "M12 4l8 6v10H4V10z",
  "M6 18V8l6-4 6 4v10",
  "M4 12h16M12 4v16",
  "M5 7h14v10H5zM9 17v3h6v-3",
  "M7 7h10v10H7zM4 10h3M17 10h3",
] as const;

function pastelForIndex(index: number): string {
  return CATEGORY_PASTELS[index % CATEGORY_PASTELS.length] ?? "var(--cat-beauty)";
}

function iconPathForIndex(index: number): string {
  return CATEGORY_ICON_PATHS[index % CATEGORY_ICON_PATHS.length] ?? CATEGORY_ICON_PATHS[0];
}

function readWideIndex(payload: Record<string, unknown>): number {
  return typeof payload.wide_index === "number" && payload.wide_index >= 0 ? payload.wide_index : 0;
}

/**
 * Optional approved Cloudinary public IDs from the category_grid merch payload.
 * Supports `{ images: { slug: "public/id" } }` or `{ category_images: [...] }`.
 */
export function readCategoryImageMap(
  payload: Record<string, unknown> | undefined,
): Map<string, string> {
  const map = new Map<string, string>();
  if (!payload) {
    return map;
  }

  const images = payload.images;
  if (images && typeof images === "object" && !Array.isArray(images)) {
    for (const [slug, value] of Object.entries(images as Record<string, unknown>)) {
      if (typeof value === "string" && value.trim().length > 0) {
        map.set(slug, value.trim());
      }
    }
  }

  const list = payload.category_images;
  if (Array.isArray(list)) {
    for (const entry of list) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const record = entry as Record<string, unknown>;
      const slug = typeof record.slug === "string" ? record.slug : null;
      const publicId =
        typeof record.image_public_id === "string"
          ? record.image_public_id
          : typeof record.public_id === "string"
            ? record.public_id
            : null;
      if (slug && publicId && publicId.trim().length > 0) {
        map.set(slug, publicId.trim());
      }
    }
  }

  return map;
}

type CategoryGridProps = {
  slot?: MerchSlotRow;
  categories: CategoryRow[];
  locale: string;
  t: CatalogTranslator;
};

function CategoryFallbackMark({ index }: { index: number }) {
  return (
    <span
      aria-hidden
      className="absolute right-3 top-3 inline-flex h-9 w-9 items-center justify-center rounded-full bg-surface/35 text-text"
      data-testid="category-fallback-icon"
    >
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        aria-hidden
      >
        <path d={iconPathForIndex(index)} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function CategoryGrid({ slot, categories, locale, t }: CategoryGridProps) {
  if (categories.length === 0) {
    return null;
  }

  const wideIndex = slot ? readWideIndex(slot.payload) : 0;
  const imageMap = readCategoryImageMap(slot?.payload);

  return (
    <section aria-labelledby="home-categories-heading" className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-categories-heading" className="font-display text-h2 text-display-ink">
          {t("home.categories.title")}
        </h2>
        <Link href={`/${locale}/categories`} className="shrink-0 text-sm font-medium text-primary">
          {t("home.categories.viewAll")}
        </Link>
      </div>
      <ul
        className="flex list-none gap-2 overflow-x-auto p-0 pb-1 [-ms-overflow-style:none] [scrollbar-width:none] snap-x snap-mandatory md:grid md:grid-cols-4 md:gap-2.5 md:overflow-visible md:pb-0 md:snap-none lg:grid-cols-6 xl:grid-cols-8 xl:gap-3 [&::-webkit-scrollbar]:hidden"
        data-testid="home-category-grid"
      >
        {categories.map((category, index) => {
          const isWide = index === wideIndex;
          const fill = pastelForIndex(index);
          const imagePublicId = imageMap.get(category.slug);

          return (
            <li
              key={category.id}
              className={`min-w-[7.75rem] snap-start md:min-w-0 ${isWide ? "md:col-span-2" : ""}`}
            >
              <Link
                href={`/${locale}/c/${category.slug}`}
                aria-label={t("home.categories.browseLabel", { category: category.name })}
                className="relative flex min-h-11 flex-col justify-end overflow-hidden rounded-[var(--r-lg)] p-3 text-text shadow-1 focus-visible:outline-none focus-visible:shadow-focusRing"
                style={{
                  backgroundColor: fill,
                  minHeight: isWide ? "5.5rem" : "4.5rem",
                }}
                data-testid={`home-category-${category.slug}`}
              >
                {imagePublicId ? (
                  <span className="absolute inset-0" data-testid="category-image">
                    <CloudinaryImage
                      publicId={imagePublicId}
                      alt=""
                      width={480}
                      ratio="4/3"
                      sizes="(max-width: 768px) 42vw, 25vw"
                      className="h-full w-full object-cover opacity-90"
                    />
                    <span
                      aria-hidden
                      className="absolute inset-0 bg-gradient-to-t from-black/45 via-black/10 to-transparent"
                    />
                  </span>
                ) : (
                  <CategoryFallbackMark index={index} />
                )}
                <span
                  className={`relative font-display text-sm font-semibold leading-snug sm:text-base ${imagePublicId ? "text-surface" : ""}`}
                >
                  {category.name}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
