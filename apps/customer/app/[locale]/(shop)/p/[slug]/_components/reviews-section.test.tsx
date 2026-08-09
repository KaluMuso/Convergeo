// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isVerifiedPurchase, ReviewsSection, type ReviewsSectionLabels } from "./reviews-section";

const insertMock = vi.fn();
const getUserMock = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { getUser: getUserMock },
    from: (table: string) => ({
      insert: (payload: unknown) => insertMock(table, payload),
    }),
  }),
}));

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("@vergeo/ui/src/media/image-gallery", () => ({
  ImageGallery: () => <div data-testid="image-gallery" />,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const labels: ReviewsSectionLabels = {
  heading: "Customer reviews",
  empty: "No reviews yet",
  writeCta: "Write a review",
  starsAria: "{rating} out of 5 stars",
  photoAlt: "Review photo",
  vendorReply: "Seller reply",
  galleryPrevious: "Previous photo",
  galleryNext: "Next photo",
  galleryIndicator: "Photo {current} of {total}",
  starFilled: "★",
  starEmpty: "☆",
  distributionHeading: "Rating breakdown",
  distributionRowAria: "{star}★: {count}",
  verifiedPurchase: "Verified purchase",
  lightboxTitle: "Review photos",
  report: {
    cta: "Report",
    heading: "Report this review",
    reasonLegend: "Tell us what needs checking.",
    submit: "Submit report",
    cancel: "Cancel",
    success: "Thanks — our moderation team will review it.",
    signedOut: "Sign in to report a review.",
    error: "Could not submit this report. Please try again.",
    reasons: [
      { value: "spam", label: "Spam or advertising" },
      { value: "abuse", label: "Abusive or hateful content" },
    ],
  },
};

describe("isVerifiedPurchase", () => {
  it("prefers the explicit verified_purchase field from the API", () => {
    expect(isVerifiedPurchase({ order_item_id: "item-1", verified_purchase: true })).toBe(true);
    expect(isVerifiedPurchase({ order_item_id: "item-1", verified_purchase: false })).toBe(false);
  });

  it("falls back to non-empty order_item_id as the DB verified-purchase gate", () => {
    expect(isVerifiedPurchase({ order_item_id: "item-1" })).toBe(true);
    expect(isVerifiedPurchase({ order_item_id: "" })).toBe(false);
  });
});

describe("ReviewsSection report control", () => {
  it("inserts a review flag through the RLS-guarded browser client", async () => {
    const user = userEvent.setup();
    getUserMock.mockResolvedValue({ data: { user: { id: "user-1" } } });
    insertMock.mockResolvedValue({ error: null });

    render(
      <ReviewsSection
        locale="en"
        labels={labels}
        reviews={[
          {
            id: "review-1",
            order_item_id: "item-1",
            verified_purchase: true,
            rating: 4,
            body: "Helpful seller.",
            photos: [],
            vendor_reply: null,
            vendor_reply_at: null,
            created_at: "2026-07-20T00:00:00Z",
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Report" }));
    await user.click(screen.getByLabelText("Abusive or hateful content"));
    await user.click(screen.getByRole("button", { name: "Submit report" }));

    await waitFor(() => {
      expect(insertMock).toHaveBeenCalledWith("flags", {
        entity_type: "review",
        entity_id: "review-1",
        reason: "abuse",
        reporter_user_id: "user-1",
      });
    });
    expect(screen.getByRole("status")).toHaveTextContent("moderation team");
  });
});

describe("ReviewsSection verified purchase", () => {
  it("shows the verified purchase badge when the authoritative signal is true", () => {
    render(
      <ReviewsSection
        locale="en"
        labels={labels}
        reviews={[
          {
            id: "review-1",
            order_item_id: "item-1",
            verified_purchase: true,
            rating: 5,
            body: "Great phone.",
            photos: [],
            vendor_reply: null,
            vendor_reply_at: null,
            created_at: "2026-07-20T00:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("review-verified-review-1")).toHaveTextContent("Verified purchase");
  });

  it("hides the badge when verified_purchase is explicitly false", () => {
    render(
      <ReviewsSection
        locale="en"
        labels={labels}
        reviews={[
          {
            id: "review-2",
            order_item_id: "",
            verified_purchase: false,
            rating: 3,
            body: null,
            photos: [],
            vendor_reply: null,
            vendor_reply_at: null,
            created_at: "2026-07-20T00:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.queryByTestId("review-verified-review-2")).not.toBeInTheDocument();
  });
});

describe("ReviewsSection photo lightbox", () => {
  it("opens a shared Modal lightbox with accessible name and closes on Escape", async () => {
    const user = userEvent.setup();
    render(
      <ReviewsSection
        locale="en"
        labels={labels}
        reviews={[
          {
            id: "review-photo",
            order_item_id: "item-photo",
            verified_purchase: true,
            rating: 5,
            body: null,
            photos: ["reviews/photo-1"],
            vendor_reply: null,
            vendor_reply_at: null,
            created_at: "2026-07-20T00:00:00Z",
          },
        ]}
      />,
    );

    const trigger = screen.getByTestId("review-photo-reviews/photo-1");
    await user.click(trigger);

    const lightbox = screen.getByTestId("review-photo-lightbox");
    expect(lightbox).toHaveAttribute("role", "dialog");
    expect(lightbox).toHaveAccessibleName("Review photos");
    expect(screen.getByTestId("image-gallery")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByTestId("review-photo-lightbox")).not.toBeInTheDocument();
    });
  });
});

describe("ReviewsSection rating distribution", () => {
  const makeReview = (id: string, rating: number) => ({
    id,
    order_item_id: `item-${id}`,
    verified_purchase: true,
    rating,
    body: null,
    photos: [],
    vendor_reply: null,
    vendor_reply_at: null,
    created_at: "2026-07-20T00:00:00Z",
  });

  it("renders a 5→1 breakdown with per-star counts", () => {
    render(
      <ReviewsSection
        locale="en"
        labels={labels}
        reviews={[makeReview("a", 5), makeReview("b", 5), makeReview("c", 4)]}
      />,
    );

    expect(screen.getByTestId("review-distribution")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Rating breakdown" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "5★: 2" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "4★: 1" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "3★: 0" })).toBeInTheDocument();
  });

  it("omits the breakdown when there are no reviews", () => {
    render(<ReviewsSection locale="en" labels={labels} reviews={[]} />);
    expect(screen.queryByTestId("review-distribution")).not.toBeInTheDocument();
  });
});
