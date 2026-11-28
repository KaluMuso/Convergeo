import { CategoryIcon } from "@vergeo/ui/src/category-icon-map";
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

function pastelForIndex(index: number): string {
  return CATEGORY_PASTELS[index % CATEGORY_PASTELS.length] ?? "var(--cat-beauty)";
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

export function CategoryGrid({ slot, categories, locale, t }: CategoryGridProps) {
  if (categories.length === 0) {
    return null;
  }

  const imageMap = readCategoryImageMap(slot?.payload);

  return (
    <section aria-labelledby="home-categories-heading" className="motion-rise flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2
          id="home-categories-heading"
          className="font-display text-h3 font-bold text-display-ink"
        >
          {t("home.categories.title")}
        </h2>
        <Link
          href={`/${locale}/categories`}
          className="-my-2.5 shrink-0 rounded-sm px-2 py-3 text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("home.categories.viewAll")}
        </Link>
      </div>
      <Rail
        as="ul"
        snap
        className="flex list-none gap-2 p-0 pb-1 md:grid md:grid-cols-6 md:gap-3 md:overflow-visible md:pb-0 md:snap-none lg:grid-cols-8 xl:grid-cols-10"
        data-testid="home-category-grid"
      >
        {categories.map((category, index) => {
          const fill = pastelForIndex(index);
          // Campaign art (merch payload) > admin-set icon > built-in photography.
          const imagePublicId =
            imageMap.get(category.slug) ??
            category.icon_public_id ??
            defaultCategoryImage(category.slug);

          return (
            <li key={category.id} className="w-20 shrink-0 snap-start md:w-auto">
              <Link
                href={`/${locale}/c/${category.slug}`}
                aria-label={t("home.categories.browseLabel", { category: category.name })}
                className="group flex min-h-11 flex-col items-center gap-1.5 rounded-lg text-center text-text focus-visible:outline-none focus-visible:shadow-focusRing"
                data-testid={`home-category-${category.slug}`}
              >
                <span
                  className="relative block aspect-square w-full overflow-hidden rounded-full border border-border"
                  style={{ backgroundColor: fill }}
                >
                  {imagePublicId ? (
                    <span className="absolute inset-0" data-testid="category-image">
                      <CloudinaryImageStatic
                        publicId={imagePublicId}
                        alt=""
                        width={192}
                        ratio="1/1"
                        sizes="(max-width: 768px) 76px, 96px"
                        className="h-full w-full object-cover transition-transform duration-slow ease-std group-hover:scale-105 motion-reduce:transition-none"
                      />
                    </span>
                  ) : (
                    <span
                      className="absolute inset-0 flex items-center justify-center"
                      data-testid="category-fallback-icon"
                    >
                      <CategoryIcon categorySlug={category.slug} size={48} />
                    </span>
                  )}
                </span>
                <span className="line-clamp-2 min-h-10 w-full text-xs font-medium leading-snug text-text group-hover:text-primary md:min-h-11">
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
