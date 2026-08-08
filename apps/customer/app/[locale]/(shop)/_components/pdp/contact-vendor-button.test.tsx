// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useSession } from "@vergeo/auth/use-session";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { ContactVendorButton, type ContactVendorLabels } from "./contact-vendor-button";

const labels = catalogMessages.pdp.contactVendor as ContactVendorLabels;

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/p/tecno-spark-20",
}));

const createEnquiry = vi.fn();

vi.mock("../../../../../lib/enquiries-api", () => ({
  createEnquiriesApiClient: () => ({
    createEnquiry: (...args: unknown[]) => createEnquiry(...args),
  }),
  ENQUIRY_BODY_MAX_CHARS: 2000,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ContactVendorButton", () => {
  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      session: { access_token: "token-abc" },
      loading: false,
    } as ReturnType<typeof useSession>);
    createEnquiry.mockResolvedValue({
      thread: { id: "thread-1" },
      message: { id: "msg-1" },
      reused_existing_thread: false,
    });
  });

  it("opens the dialog and sends a listing-anchored enquiry", async () => {
    const user = userEvent.setup();
    render(
      <ContactVendorButton
        locale="en"
        listingId="listing-uuid"
        vendorName="Demo Vendor"
        labels={labels}
      />,
    );

    await user.click(screen.getByTestId("pdp-contact-vendor-cta"));
    expect(screen.getByTestId("pdp-contact-vendor-dialog")).toBeInTheDocument();

    await user.type(screen.getByTestId("pdp-contact-vendor-message"), "Is this still in stock?");
    await user.click(screen.getByTestId("pdp-contact-vendor-submit"));

    await waitFor(() => {
      expect(createEnquiry).toHaveBeenCalledWith({
        subject_kind: "listing",
        subject_id: "listing-uuid",
        body: "Is this still in stock?",
      });
    });
    expect(screen.getByTestId("pdp-contact-vendor-success")).toBeInTheDocument();
  });

  it("prompts sign-in when the visitor is anonymous", async () => {
    vi.mocked(useSession).mockReturnValue({
      session: null,
      loading: false,
    } as ReturnType<typeof useSession>);

    const user = userEvent.setup();
    render(
      <ContactVendorButton
        locale="en"
        listingId="listing-uuid"
        vendorName="Demo Vendor"
        labels={labels}
      />,
    );

    await user.click(screen.getByTestId("pdp-contact-vendor-cta"));
    expect(screen.getByTestId("pdp-contact-vendor-sign-in")).toHaveAttribute(
      "href",
      "/en/login?next=%2Fen%2Fp%2Ftecno-spark-20",
    );
  });

  it("shows validation error for an empty message", async () => {
    const user = userEvent.setup();
    render(
      <ContactVendorButton
        locale="en"
        listingId="listing-uuid"
        vendorName="Demo Vendor"
        labels={labels}
      />,
    );

    await user.click(screen.getByTestId("pdp-contact-vendor-cta"));
    await user.click(screen.getByTestId("pdp-contact-vendor-submit"));

    expect(createEnquiry).not.toHaveBeenCalled();
    expect(screen.getByText(labels.errors.empty)).toBeInTheDocument();
  });

  it("closes the dialog on Escape", async () => {
    const user = userEvent.setup();
    render(
      <ContactVendorButton
        locale="en"
        listingId="listing-uuid"
        vendorName="Demo Vendor"
        labels={labels}
      />,
    );

    await user.click(screen.getByTestId("pdp-contact-vendor-cta"));
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByTestId("pdp-contact-vendor-dialog")).not.toBeInTheDocument();
    });
  });
});
