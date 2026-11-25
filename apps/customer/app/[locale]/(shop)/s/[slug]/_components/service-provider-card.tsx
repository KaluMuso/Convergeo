"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { StarRating } from "@vergeo/ui/src/star-rating";
import Link from "next/link";

export type ServiceProviderCardLabels = {
  heading: string;
  preferredBadge: string;
  reviewCount: string;
  starsAria: string;
  viewProfile: string;
};

type ServiceProviderCardProps = {
  locale: string;
  displayName: string;
  slug: string;
  preferredBadge: boolean;
  ratingAvg: number | null;
  ratingCount: number;
  labels: ServiceProviderCardLabels;
};

function starsAria(template: string, rating: number): string {
  return template.replace("{rating}", String(Math.round(rating * 10) / 10));
}

export function ServiceProviderCard({
  locale,
  displayName,
  slug,
  preferredBadge,
  ratingAvg,
  ratingCount,
  labels,
}: ServiceProviderCardProps) {
  const showRating = ratingCount > 0 && ratingAvg !== null;

  return (
    <section
      className="rounded-lg border border-border bg-surface p-5 shadow-1"
      aria-labelledby="service-provider-card-heading"
    >
      <p
        id="service-provider-card-heading"
        className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3"
      >
        {labels.heading}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <p className="font-semibold text-text">{displayName}</p>
        {preferredBadge ? <Badge variant="public" label={labels.preferredBadge} /> : null}
      </div>
      {showRating ? (
        <div
          className="mt-2 flex items-center gap-2"
          role="img"
          aria-label={starsAria(labels.starsAria, ratingAvg)}
        >
          <StarRating mode="display" value={ratingAvg} />
          <span className="text-sm text-text-2">{labels.reviewCount}</span>
        </div>
      ) : null}
      {slug ? (
        <Link
          href={`/${locale}/v/${slug}`}
          className="mt-3 inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {labels.viewProfile}
        </Link>
      ) : null}
    </section>
  );
}
