/** Customer popular searches — server-rendered from anonymized search_query_log aggregates. */

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { fetchJson } from "../../../../lib/fetch-json";
import Link from "next/link";

type PopularSearchItem = {
  term: string;
  count: number;
};

type PopularSearchesResponse = {
  items: PopularSearchItem[];
};

export type PopularSearchesLabels = {
  title: string;
};

export type PopularSearchesProps = {
  locale: string;
  labels: PopularSearchesLabels;
  className?: string;
};

export async function PopularSearches({ locale, labels, className }: PopularSearchesProps) {
  const url = absoluteApiUrl("/discovery/popular-searches?limit=6");
  if (!url) {
    return null;
  }

  let items: PopularSearchItem[] = [];
  try {
    const data = await fetchJson<PopularSearchesResponse>(url, {
      next: { revalidate: 300 },
    });
    items = data.items ?? [];
  } catch {
    return null;
  }

  if (items.length === 0) {
    return null;
  }

  return (
    <section className={className} aria-label={labels.title}>
      <h2 className="mb-2 text-sm font-semibold text-text">{labels.title}</h2>
      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.term}>
            <Link
              href={`/${locale}/search?q=${encodeURIComponent(item.term)}`}
              className="inline-flex min-h-11 items-center rounded-pill border border-border bg-surface px-3 text-sm text-text hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {item.term}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
