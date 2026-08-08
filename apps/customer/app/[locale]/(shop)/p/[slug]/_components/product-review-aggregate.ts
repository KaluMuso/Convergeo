/**
 * Product JSON-LD AggregateRating helpers.
 *
 * Authoritative source: GET /reviews?product_id= → ProductReviewsResponse
 * (`rating_avg`, `rating_count`) — arithmetic mean over the full published set
 * (unpaginated), matching the vendor-page `reviews_summary` pattern. Never use
 * a UI page sample size as reviewCount.
 */

export type ProductReviewAggregate = {
  rating_avg: number | null;
  rating_count: number;
};

export type JsonLdAggregateRating = {
  ratingValue: number;
  reviewCount: number;
};

/**
 * Emit schema.org AggregateRating only when genuine values exist:
 * count > 0 and rating in [1, 5].
 */
export function productAggregateRatingForJsonLd(
  aggregate: ProductReviewAggregate | null | undefined,
): JsonLdAggregateRating | null {
  if (!aggregate) {
    return null;
  }
  const { rating_avg: ratingAvg, rating_count: ratingCount } = aggregate;
  if (
    typeof ratingCount !== "number" ||
    !Number.isInteger(ratingCount) ||
    ratingCount <= 0 ||
    typeof ratingAvg !== "number" ||
    !Number.isFinite(ratingAvg) ||
    ratingAvg < 1 ||
    ratingAvg > 5
  ) {
    return null;
  }
  return { ratingValue: ratingAvg, reviewCount: ratingCount };
}
