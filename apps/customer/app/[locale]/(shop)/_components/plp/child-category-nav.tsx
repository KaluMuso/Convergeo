import Link from "next/link";

export type ChildCategoryLink = {
  slug: string;
  name: string;
};

type ChildCategoryNavProps = {
  locale: string;
  heading: string;
  categories: ChildCategoryLink[];
  /** Parent path segments for nested URLs, e.g. ["electronics"]. Empty for top-level. */
  parentSlugParts?: string[];
};

/**
 * Server-rendered child-category discovery strip for PLP — keeps SEO text and avoids promo bloat.
 */
export function ChildCategoryNav({
  locale,
  heading,
  categories,
  parentSlugParts = [],
}: ChildCategoryNavProps) {
  if (categories.length === 0) {
    return null;
  }

  return (
    <nav aria-label={heading} data-testid="plp-child-categories" className="flex flex-col gap-2">
      <p className="text-sm font-medium text-text">{heading}</p>
      <ul className="flex list-none flex-wrap gap-2 p-0">
        {categories.map((category) => {
          const href = `/${locale}/c/${[...parentSlugParts, category.slug].join("/")}`;
          return (
            <li key={category.slug}>
              <Link
                href={href}
                className="inline-flex min-h-11 items-center rounded-pill border border-border bg-surface px-3 text-sm text-text transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {category.name}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
