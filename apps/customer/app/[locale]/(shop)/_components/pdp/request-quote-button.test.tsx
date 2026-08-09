// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useSession } from "@vergeo/auth/use-session";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { RequestQuoteButton, type RequestQuoteLabels } from "./request-quote-button";

const labels = catalogMessages.pdp.requestQuote as RequestQuoteLabels;

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/p/tecno-spark-20",
}));

const createRfq = vi.fn();

vi.mock("../../../../../lib/rfq-api", () => ({
  createRfqApiClient: () => ({
    createRfq: (...args: unknown[]) => createRfq(...args),
  }),
  RFQ_DETAILS_MAX_CHARS: 2000,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RequestQuoteButton", () => {
  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      session: { access_token: "token-abc" },
      loading: false,
    } as ReturnType<typeof useSession>);
    createRfq.mockResolvedValue({
      thread: { id: "thread-1" },
      message: { id: "msg-1" },
      reused_existing_thread: false,
    });
  });

  it("opens the shared Modal with an accessible name and closes on Escape", async () => {
    const user = userEvent.setup();
    render(
      <RequestQuoteButton
        locale="en"
        listingId="listing-uuid"
        vendorName="Demo Vendor"
        labels={labels}
      />,
    );

    const cta = screen.getByTestId("pdp-request-quote-cta");
    await user.click(cta);
    const dialog = screen.getByTestId("pdp-request-quote-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAccessibleName(labels.dialogTitle);

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByTestId("pdp-request-quote-dialog")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(cta);
    });
  });
});
