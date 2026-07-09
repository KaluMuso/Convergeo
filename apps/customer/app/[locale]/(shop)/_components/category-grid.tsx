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

function pastelForIndex(index: number): string {
  return CATEGORY_PASTELS[index % CATEGORY_PASTELS.length] ?? "var(--cat-beauty)";
}

function readWideIndex(payload: Record<string, unknown>): number {
  return typeof payload.wide_index === "number" && payload.wide_index >= 0 ? payload.wide_index : 0;
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

  const wideIndex = slot ? readWideIndex(slot.payload) : 0;

  return (
    <section aria-labelledby="home-categories-heading" className="flex flex-col gap-3">
      <h2 id="home-categories-heading" className="font-display text-h2 text-display-ink">
        {t("home.categories.title")}
      </h2>
      <ul className="grid list-none grid-cols-2 gap-3 p-0">
        {categories.map((category, index) => {
          const isWide = index === wideIndex;
          const fill = pastelForIndex(index);

          return (
            <li key={category.id} className={isWide ? "col-span-2" : undefined}>
              <Link
                href={`/${locale}/c/${category.slug}`}
                className="flex min-h-11 flex-col justify-end rounded-lg p-4 text-text shadow-1"
                style={{
                  backgroundColor: fill,
                  minHeight: isWide ? "7.5rem" : "6rem",
                }}
              >
                <span className="font-display text-h3">{category.name}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
