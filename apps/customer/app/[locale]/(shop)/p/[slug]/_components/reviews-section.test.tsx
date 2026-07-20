// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewsSection, type ReviewsSectionLabels } from "./reviews-section";

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
