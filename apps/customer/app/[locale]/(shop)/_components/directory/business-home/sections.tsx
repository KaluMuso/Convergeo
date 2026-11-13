import { formatK } from "@vergeo/i18n";
import Image from "next/image";
import Link from "next/link";

import { OpenStatus, type DaySchedule } from "./open-status";

import type { ReactNode } from "react";

/**
 * Business Home blocks for /v/[slug] (growth blueprint §8.3). Server components:
 * no client JS except the tiny OpenStatus island. Every label arrives
 * pre-translated from the page, so these stay locale-agnostic and testable.
 */

function SectionHeading({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="m-0 font-display text-h3 font-semibold text-display-ink">
      {children}
    </h2>
  );
}

export function StorySection({ heading, story }: { heading: string; story: string | null }) {
  const text = story?.trim();
  if (!text) {
    return null;
  }
  return (
    <section
      aria-labelledby="bh-story"
      data-testid="bh-story"
      className="space-y-2 rounded-lg border border-border bg-surface p-4"
    >
      <SectionHeading id="bh-story">{heading}</SectionHeading>
      <p className="m-0 max-w-prose whitespace-pre-line text-body text-text-2">{text}</p>
    </section>
  );
}

export type BusinessBranch = {
  landmark: string;
  lat: number;
  lng: number;
  schedule: DaySchedule[];
};

export function directionsHref(branch: Pick<BusinessBranch, "lat" | "lng">) {
  return `https://www.google.com/maps/dir/?api=1&destination=${branch.lat},${branch.lng}`;
}

export type FindUsLabels = {
  heading: string;
  directions: string;
  directionsTo: (place: string) => string;
  hoursNotShared: string;
  hoursRange: (opens: string, closes: string) => string;
  day: (day: DaySchedule["day"]) => string;
  open: string;
  closed: string;
};

export function FindUsSection({
  branches,
  labels,
}: {
  branches: BusinessBranch[];
  labels: FindUsLabels;
}) {
  if (branches.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="bh-find-us" data-testid="bh-find-us" className="space-y-3">
      <SectionHeading id="bh-find-us">{labels.heading}</SectionHeading>
      <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2">
        {branches.map((branch, index) => (
          <li
            key={`${branch.landmark}-${index}`}
            data-testid="bh-branch"
            className="space-y-2 rounded-lg border border-border bg-surface p-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="m-0 font-semibold text-text">{branch.landmark}</p>
              <OpenStatus
                schedule={branch.schedule}
                labels={{ open: labels.open, closed: labels.closed }}
              />
            </div>
            {branch.schedule.length > 0 ? (
              <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-sm">
                {branch.schedule.map((entry) => (
                  <div key={entry.day} className="contents">
                    <dt className="text-text-2">{labels.day(entry.day)}</dt>
                    <dd className="m-0 text-text">
                      {labels.hoursRange(entry.opens, entry.closes)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="m-0 text-sm text-text-2">{labels.hoursNotShared}</p>
            )}
            <a
              href={directionsHref(branch)}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={labels.directionsTo(branch.landmark)}
              className="inline-flex min-h-11 items-center gap-2 rounded border border-border px-3 text-sm font-semibold text-primary no-underline hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              <svg
                aria-hidden
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 21s-7-6.2-7-11a7 7 0 1 1 14 0c0 4.8-7 11-7 11Z" />
                <circle cx="12" cy="10" r="2.5" />
              </svg>
              {labels.directions}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export type BusinessClip = {
  id: string;
  poster_url: string | null;
  caption: string | null;
};

/** Poster-only row: no video bytes until the customer taps into /clips/[id]. */
export function ClipsRow({
  locale,
  clips,
  labels,
}: {
  locale: string;
  clips: BusinessClip[];
  labels: { heading: string; watch: string };
}) {
  if (clips.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="bh-clips" data-testid="bh-clips" className="space-y-2">
      <SectionHeading id="bh-clips">{labels.heading}</SectionHeading>
      <ul className="-mx-1 m-0 flex list-none gap-2 overflow-x-auto p-0 px-1 [scrollbar-width:none]">
        {clips.map((clip) => (
          <li key={clip.id} className="shrink-0">
            <Link
              href={`/${locale}/clips/${encodeURIComponent(clip.id)}`}
              aria-label={clip.caption ? `${labels.watch}: ${clip.caption}` : labels.watch}
              className="relative block h-40 w-24 overflow-hidden rounded-lg bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {clip.poster_url ? (
                <Image
                  src={clip.poster_url}
                  alt=""
                  fill
                  sizes="96px"
                  loading="lazy"
                  className="object-cover"
                />
              ) : null}
              <svg
                aria-hidden
                viewBox="0 0 24 24"
                className="absolute bottom-2 left-2 h-5 w-5 text-surface"
                fill="currentColor"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Offers block. No coupons table exists on this base yet: the API only reports
 * the `business_offers` flag (default OFF), and while it is off nothing renders.
 */
export function OffersSection({
  enabled,
  labels,
}: {
  enabled: boolean;
  labels: { heading: string; empty: string };
}) {
  if (!enabled) {
    return null;
  }
  return (
    <section
      aria-labelledby="bh-offers"
      data-testid="bh-offers"
      className="space-y-2 rounded-lg border border-dashed border-border bg-surface p-4"
    >
      <SectionHeading id="bh-offers">{labels.heading}</SectionHeading>
      <p className="m-0 text-sm text-text-2">{labels.empty}</p>
    </section>
  );
}

export function ReviewsSection({
  ratingAvg,
  ratingCount,
  labels,
}: {
  ratingAvg: number | null;
  ratingCount: number;
  labels: {
    heading: string;
    summary: string;
    none: string;
    verifiedOnly: string;
  };
}) {
  const hasRating = ratingAvg !== null && ratingCount > 0;
  return (
    <section aria-labelledby="bh-reviews" data-testid="bh-reviews" className="space-y-2">
      <SectionHeading id="bh-reviews">{labels.heading}</SectionHeading>
      <div className="flex flex-wrap items-center gap-3 text-body text-text-2">
        {hasRating ? (
          <>
            <span className="font-display text-h2 font-bold text-display-ink">
              {ratingAvg.toFixed(1)}
            </span>
            <span>{labels.summary}</span>
          </>
        ) : (
          <span>{labels.none}</span>
        )}
      </div>
      <p className="m-0 text-sm text-text-2">{labels.verifiedOnly}</p>
    </section>
  );
}

export type ServiceLabels = {
  from: (price: string) => string;
  book: (price: string) => string;
  quote: string;
  area: (area: string) => string;
};

/** Customer-first price line: fixed booking price, else "from", else quote. */
export function servicePriceLine(
  service: {
    bookable?: boolean;
    booking_price_ngwee?: number | null;
    from_price_ngwee: number | null;
  },
  labels: ServiceLabels,
): string {
  if (service.bookable && typeof service.booking_price_ngwee === "number") {
    return labels.book(formatK(service.booking_price_ngwee));
  }
  if (service.from_price_ngwee !== null) {
    return labels.from(formatK(service.from_price_ngwee));
  }
  return labels.quote;
}
