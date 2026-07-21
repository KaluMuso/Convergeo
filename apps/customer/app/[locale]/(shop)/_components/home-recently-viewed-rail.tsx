"use client";

import Link from "next/link";

import { RECENTLY_VIEWED_MAX, useRecentlyViewed } from "./recently-viewed/use-recently-viewed";

const HOME_RECENT_LIMIT = 12;

export type HomeRecentlyViewedRailLabels = {
  title: string;
  viewAll: string;
  /** Accessible name template — `{name}` is the product title. */
  viewProduct: string;
  /** Visible CTA on each chip. */
  view: string;
};

type HomeRecentlyViewedRailProps = {
  locale: string;
  labels: HomeRecentlyViewedRailLabels;
};

/**
 * Client-only home rail for recently viewed products (localStorage).
 * Renders nothing until hydrated and non-empty — never invents history.
 */
export function HomeRecentlyViewedRail({ locale, labels }: HomeRecentlyViewedRailProps) {
  const { entries, hydrated } = useRecentlyViewed();

  if (!hydrated || entries.length === 0) {
    return null;
  }

  const visible = entries.slice(0, Math.min(HOME_RECENT_LIMIT, RECENTLY_VIEWED_MAX));

  return (
    <section
      aria-labelledby="home-rail-recent"
      className="flex flex-col gap-3 motion-fade lg:gap-4"
      data-testid="home-recently-viewed-rail"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-rail-recent" className="font-display text-h2 text-display-ink">
          {labels.title}
        </h2>
        <Link
          href={`/${locale}/account/recent`}
          className="shrink-0 text-sm font-medium text-primary"
        >
          {labels.viewAll}
        </Link>
      </div>
      <ul
        className="flex list-none gap-3 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        data-testid="home-recently-viewed-list"
      >
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
              <span className="text-xs font-medium text-primary" aria-hidden="true">
                {labels.view}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
