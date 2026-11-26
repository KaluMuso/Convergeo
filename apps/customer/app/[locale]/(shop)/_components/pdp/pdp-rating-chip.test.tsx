// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PdpRatingChip } from "./pdp-rating-chip";

afterEach(cleanup);

describe("PdpRatingChip", () => {
  it("links to the reviews section anchor", () => {
    render(
      <PdpRatingChip
        locale="en"
        productSlug="phone-x"
        ratingAvg={4.5}
        ratingCount={10}
        photoReviewCount={2}
        starsAriaLabel="4.5 stars"
        ratingSummary="4.5 (10)"
        photoReviewsLink="Photo reviews"
      />,
    );
    expect(screen.getByRole("link", { name: "4.5 stars" })).toHaveAttribute(
      "href",
      "/en/p/phone-x#pdp-reviews",
    );
    expect(screen.getByTestId("pdp-photo-reviews-link")).toHaveAttribute(
      "href",
      "/en/p/phone-x#pdp-reviews",
    );
  });
});
