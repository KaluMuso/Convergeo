// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportListing, type ReportListingLabels } from "./report-listing";

const getSession = vi.fn();
const fetchMock = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: vi.fn(async () => ({
    auth: { getSession },
  })),
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://localhost:8000",
}));

const labels: ReportListingLabels = {
  cta: "Report listing",
  heading: "Report this listing",
  reasonLegend: "What is wrong?",
  detailLabel: "More details",
  detailPlaceholder: "Optional",
  submit: "Submit report",
  cancel: "Cancel",
  success: "Thanks",
  signedOut: "Sign in",
  error: "Failed",
  rateLimited: "Slow down",
  reasons: [
    { value: "scam", label: "Scam" },
    { value: "other", label: "Other" },
  ],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  getSession.mockResolvedValue({
    data: { session: { access_token: "tok" } },
  });
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ ok: true, created: true, deduped: false, flag_id: "f1" }),
  });
  vi.stubGlobal("fetch", fetchMock);
});

describe("ReportListing", () => {
  it("posts to the API with bearer auth (not raw Supabase insert)", async () => {
    render(<ReportListing listingId="listing-1" labels={labels} />);
    fireEvent.click(screen.getByTestId("pdp-report-listing-cta"));
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/flags/report",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Authorization: "Bearer tok",
          }),
        }),
      );
    });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      listing_id: "listing-1",
      reason: "scam",
      detail: null,
    });
    expect(await screen.findByText("Thanks")).toBeInTheDocument();
  });

  it("shows signed-out messaging when session is missing", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    render(<ReportListing listingId="listing-1" labels={labels} />);
    fireEvent.click(screen.getByTestId("pdp-report-listing-cta"));
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    expect(await screen.findByText("Sign in")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
