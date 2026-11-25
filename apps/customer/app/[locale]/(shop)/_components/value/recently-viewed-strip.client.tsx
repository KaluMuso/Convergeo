"use client";

import { formatK } from "@vergeo/i18n";
import { Rail } from "@vergeo/ui/src/rail";
import Link from "next/link";

import { useRecentlyViewed } from "../recently-viewed/use-recently-viewed";

const DETAIL_RECENT_LIMIT = 6;

export type RecentlyViewedStripLabels = {
  title: string;
  viewProduct: string;
};

type RecentlyViewedStripClientProps = {
  locale: string;
  currentSlug: string;
  labels: RecentlyViewedStripLabels;
};

export function RecentlyViewedStripClient({
  locale,
  currentSlug,
  labels,
}: RecentlyViewedStripClientProps) {
  const { entries, hydrated } = useRecentlyViewed();

  if (!hydrated) {
    return null;
  }

  const visible = entries
    .filter((entry) => entry.slug !== currentSlug)
    .slice(0, DETAIL_RECENT_LIMIT);

  if (visible.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="value-recently-viewed-title"
      className="flex flex-col gap-3 motion-fade"
      data-testid="value-recently-viewed-strip"
    >
      <h2 id="value-recently-viewed-title" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h2>
      <Rail as="ul" className="flex list-none gap-3 pb-1" data-testid="value-recently-viewed-list">
        {visible.map((entry) => (
          <li
            key={`${entry.slug}-${entry.viewedAt}`}
            className="min-w-[10.5rem] max-w-[14rem] shrink-0"
          >
            <Link
              href={`/${locale}/p/${entry.slug}`}
              className="flex h-full min-h-11 flex-col justify-between gap-2 rounded-lg border border-border bg-surface p-3 no-underline shadow-1 transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
              aria-label={labels.viewProduct.replace("{name}", entry.name)}
            >
              <span className="line-clamp-2 font-medium leading-snug text-text">{entry.name}</span>
              {typeof entry.priceNgwee === "number" ? (
                <span className="text-sm font-semibold text-text">{formatK(entry.priceNgwee)}</span>
              ) : null}
            </Link>
          </li>
        ))}
      </Rail>
    </section>
  );
}
