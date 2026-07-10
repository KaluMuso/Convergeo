"use client";

import Link from "next/link";

export const SERVICE_VERTICALS = [
  "beauty",
  "food-catering",
  "auto",
  "printing-creative",
  "home-services",
  "tech-services",
  "cleaning",
  "tailoring",
] as const;

type VerticalFilterChipsProps = {
  locale: string;
  labels: {
    verticalLabel: string;
    areaLabel: string;
    areaPlaceholder: string;
    categories: Record<string, string>;
  };
  activeCategory: string | null;
  activeArea: string;
  verticals: readonly string[];
};

export function VerticalFilterChips({
  locale,
  labels,
  activeCategory,
  activeArea,
  verticals,
}: VerticalFilterChipsProps) {
  function hrefFor(category: string | null, area: string): string {
    const params = new URLSearchParams();
    if (category) {
      params.set("category", category);
    }
    if (area.trim()) {
      params.set("area", area.trim());
    }
    const suffix = params.toString();
    return `/${locale}/services${suffix ? `?${suffix}` : ""}`;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-3">
          {labels.verticalLabel}
        </p>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          <Link
            href={hrefFor(null, activeArea)}
            className={`inline-flex min-h-11 shrink-0 items-center rounded-full border px-4 text-sm font-medium ${
              activeCategory === null
                ? "border-primary bg-primary text-surface"
                : "border-border bg-surface text-text-2"
            }`}
          >
            {labels.categories.all}
          </Link>
          {verticals.map((vertical) => (
            <Link
              key={vertical}
              href={hrefFor(vertical, activeArea)}
              className={`inline-flex min-h-11 shrink-0 items-center rounded-full border px-4 text-sm font-medium ${
                activeCategory === vertical
                  ? "border-primary bg-primary text-surface"
                  : "border-border bg-surface text-text-2"
              }`}
            >
              {labels.categories[vertical] ?? vertical}
            </Link>
          ))}
        </div>
      </div>

      <form action={`/${locale}/services`} method="get" className="flex flex-col gap-2">
        {activeCategory ? <input type="hidden" name="category" value={activeCategory} /> : null}
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-3">
            {labels.areaLabel}
          </span>
          <div className="flex gap-2">
            <input
              name="area"
              defaultValue={activeArea}
              placeholder={labels.areaPlaceholder}
              className="min-h-11 flex-1 rounded-md border border-border bg-surface px-3 text-sm"
            />
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-semibold"
            >
              Filter
            </button>
          </div>
        </label>
      </form>
    </div>
  );
}
