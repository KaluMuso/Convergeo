import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));
vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {},
  createApiClient: () => ({ request }),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => false }),
}));

import VendorJobsPage from "./page";

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("VendorJobsPage", () => {
  it("links each matched job card to its detail page", async () => {
    request.mockResolvedValue({
      items: [
        {
          id: "job-7",
          category: "plumbing",
          description: "Fix a tap",
          preferred_date: null,
          budget_band_min_ngwee: null,
          budget_band_max_ngwee: null,
          created_at: "2026-01-01T00:00:00Z",
          own_quote: null,
        },
      ],
    });
    render(<VendorJobsPage params={Promise.resolve({ locale: "fr" })} />);
    const link = await screen.findByText("viewJob");
    await vi.waitFor(() => expect(link.closest("a")?.getAttribute("href")).toBe("/fr/jobs/job-7"));
  });
});
