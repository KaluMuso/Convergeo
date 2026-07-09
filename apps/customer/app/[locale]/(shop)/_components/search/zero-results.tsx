import Link from "next/link";

export type CategorySuggestion = {
  key: string;
  href: string;
  label: string;
};

export type ZeroResultsLabels = {
  title: string;
  suggestionsTitle: string;
  categoriesTitle: string;
  suggestionTerms: string[];
  categories: CategorySuggestion[];
  askVergeoTitle: string;
  askVergeoTeaser: string;
  askVergeoSlotLabel: string;
};

export type ZeroResultsProps = {
  query: string;
  locale: string;
  labels: ZeroResultsLabels;
};

export function ZeroResults({ query: _query, locale, labels }: ZeroResultsProps) {
  return (
    <div className="space-y-6" data-testid="search-zero-results">
      <div className="rounded-lg border border-border bg-surface p-4 text-center">
        <p className="font-medium text-text">{labels.title}</p>
      </div>

      <section aria-labelledby="search-suggestion-terms">
        <h2 id="search-suggestion-terms" className="mb-2 text-sm font-semibold text-text">
          {labels.suggestionsTitle}
        </h2>
        <ul className="flex flex-wrap gap-2">
          {labels.suggestionTerms.map((term) => (
            <li key={term}>
              <Link
                href={`/${locale}/search?q=${encodeURIComponent(term)}`}
                className="inline-flex min-h-11 items-center rounded-pill border border-border bg-bg px-3 text-sm text-primary hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {term}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="search-category-suggestions">
        <h2 id="search-category-suggestions" className="mb-2 text-sm font-semibold text-text">
          {labels.categoriesTitle}
        </h2>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {labels.categories.map((category) => (
            <li key={category.key}>
              <Link
                href={category.href}
                className="flex min-h-11 items-center justify-center rounded-lg border border-border bg-surface px-3 text-center text-sm text-text hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {category.label}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="ask-vergeo-title"
        className="rounded-lg border border-dashed border-border bg-bg-2 p-4"
      >
        <h2 id="ask-vergeo-title" className="mb-1 font-display text-h3 text-display-ink">
          {labels.askVergeoTitle}
        </h2>
        <p className="mb-3 text-sm text-text-2">{labels.askVergeoTeaser}</p>
        <div
          id="ask-vergeo-slot"
          data-testid="ask-vergeo-slot"
          aria-label={labels.askVergeoSlotLabel}
          className="min-h-24 rounded-md border border-border bg-surface"
        />
      </section>
    </div>
  );
}
