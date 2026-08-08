import { describe, expect, it } from "vitest";

import { productAggregateRatingForJsonLd } from "./product-review-aggregate";

describe("productAggregateRatingForJsonLd", () => {
  it("emits AggregateRating from authoritative rating_avg / rating_count", () => {
    expect(productAggregateRatingForJsonLd({ rating_avg: 4.5, rating_count: 12 })).toEqual({
      ratingValue: 4.5,
      reviewCount: 12,
    });
  });

  it("omits AggregateRating when there are no reviews", () => {
    expect(productAggregateRatingForJsonLd({ rating_avg: null, rating_count: 0 })).toBeNull();
    expect(productAggregateRatingForJsonLd(null)).toBeNull();
  });

  it("rejects invalid rating values even when count is positive", () => {
    expect(productAggregateRatingForJsonLd({ rating_avg: 0, rating_count: 3 })).toBeNull();
    expect(productAggregateRatingForJsonLd({ rating_avg: 5.1, rating_count: 3 })).toBeNull();
    expect(productAggregateRatingForJsonLd({ rating_avg: Number.NaN, rating_count: 3 })).toBeNull();
  });

  it("rejects non-integer or negative review counts", () => {
    expect(productAggregateRatingForJsonLd({ rating_avg: 4, rating_count: 1.5 })).toBeNull();
    expect(productAggregateRatingForJsonLd({ rating_avg: 4, rating_count: -1 })).toBeNull();
  });
});
