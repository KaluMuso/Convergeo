"use client";

import { StarRating } from "@vergeo/ui/src/star-rating";

export type ServiceReviewRow = {
  id: string;
  rating: number;
  body: string | null;
  vendor_reply: string | null;
  created_at: string;
};

export type ServiceReviewsLabels = {
  heading: string;
  subheading: string;
  empty: string;
  /** Precomputed plural label for the total count, e.g. "12 reviews". */
  reviewCountLabel: string;
  /** Template containing "{rating}", substituted per row for the a11y name. */
  starsAria: string;
  vendorReply: string;
};

type ServiceReviewsSectionProps = {
  reviews: ServiceReviewRow[];
  ratingAvg: number | null;
  ratingCount: number;
  labels: ServiceReviewsLabels;
};

function starsAriaFor(template: string, rating: number): string {
  return template.replace("{rating}", String(rating));
}

/**
 * Provider reviews on the service detail page. Data is fetched server-side and
 * passed in, so the list renders in the initial HTML (SEO). "use client" only
 * because the shared StarRating relies on a React hook.
 */
export function ServiceReviewsSection({
  reviews,
  ratingAvg,
  ratingCount,
  labels,
}: ServiceReviewsSectionProps) {
  return (
    <section aria-labelledby="service-reviews-heading" className="space-y-4">
      <header className="space-y-1">
        <h2 id="service-reviews-heading" className="font-display text-h3 text-display-ink">
          {labels.heading}
        </h2>
        <p className="text-sm text-text-2">{labels.subheading}</p>
      </header>

      {ratingCount === 0 || reviews.length === 0 ? (
        <p className="text-sm text-text-2">{labels.empty}</p>
      ) : (
        <>
          <div
            className="flex items-center gap-2"
            role="img"
            aria-label={starsAriaFor(labels.starsAria, Math.round((ratingAvg ?? 0) * 10) / 10)}
          >
            <StarRating mode="display" value={ratingAvg ?? 0} />
            <span className="text-sm text-text-2">{labels.reviewCountLabel}</span>
          </div>

          <ul className="space-y-4">
            {reviews.map((review) => (
              <li key={review.id} className="space-y-2 rounded border border-border bg-surface p-4">
                <span role="img" aria-label={starsAriaFor(labels.starsAria, review.rating)}>
                  <StarRating mode="display" value={review.rating} />
                </span>
                {review.body ? <p className="text-sm text-display-ink">{review.body}</p> : null}
                {review.vendor_reply ? (
                  <div className="rounded bg-bg-2 px-3 py-2 text-sm">
                    <p className="font-medium text-display-ink">{labels.vendorReply}</p>
                    <p className="text-text-2">{review.vendor_reply}</p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
