import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { Rail } from "@vergeo/ui/src/rail";
import Link from "next/link";

import { defaultCategoryImage } from "./category-imagery";

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
      className="absolute inset-0 m-auto inline-flex h-11 w-11 items-center justify-center rounded-full bg-surface/50 text-text"
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
    <section aria-labelledby="home-categories-heading" className="motion-rise flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-categories-heading" className="font-display text-h2 text-display-ink">
          {t("home.categories.title")}
        </h2>
        <Link
          href={`/${locale}/categories`}
          className="shrink-0 rounded-sm px-2 py-1 text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("home.categories.viewAll")}
        </Link>
      </div>
      <Rail
        as="ul"
        snap
        className="flex list-none gap-3 p-0 pb-1 md:grid md:grid-cols-4 md:gap-4 md:overflow-visible md:pb-0 md:snap-none lg:grid-cols-6 xl:grid-cols-8"
        data-testid="home-category-grid"
      >
        {categories.map((category, index) => {
          const isWide = index === wideIndex;
          const fill = pastelForIndex(index);
          const imagePublicId = imageMap.get(category.slug) ?? defaultCategoryImage(category.slug);

          return (
            <li
              key={category.id}
              className={`w-[6.75rem] shrink-0 snap-start md:w-auto ${isWide ? "md:col-span-2" : ""}`}
            >
              <Link
                href={`/${locale}/c/${category.slug}`}
                aria-label={t("home.categories.browseLabel", { category: category.name })}
                className="group flex min-h-11 flex-col gap-2 rounded-lg text-text focus-visible:outline-none focus-visible:shadow-focusRing"
                data-testid={`home-category-${category.slug}`}
              >
                <span
                  className={`relative block overflow-hidden rounded-lg border border-border ${isWide ? "aspect-square md:aspect-[2/1]" : "aspect-square"}`}
                  style={{ backgroundColor: fill }}
                >
                  {imagePublicId ? (
                    <span className="absolute inset-0" data-testid="category-image">
                      <CloudinaryImageStatic
                        publicId={imagePublicId}
                        alt=""
                        width={360}
                        ratio="1/1"
                        sizes="(max-width: 768px) 28vw, (max-width: 1280px) 16vw, 12vw"
                        className="h-full w-full object-cover transition-transform duration-slow ease-std group-hover:scale-105 motion-reduce:transition-none"
                      />
                    </span>
                  ) : (
                    <CategoryFallbackMark index={index} />
                  )}
                </span>
                <span className="px-0.5 text-sm font-semibold leading-snug text-text group-hover:text-primary">
                  {category.name}
                </span>
              </Link>
            </li>
          );
        })}
      </Rail>
    </section>
  );
}
