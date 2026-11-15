import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));
vi.mock("@vergeo/config", () => ({ createApiClient: () => ({ request }) }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

import { TrialBanner, formatTrialEnd } from "./trial-banner";

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("TrialBanner", () => {
  it("formats the trial end in Lusaka time", () => {
    // 23:30 UTC on 14 Jan is already 15 Jan in Lusaka (UTC+2).
    expect(formatTrialEnd("2027-01-14T23:30:00Z", "en")).toBe("Jan 15, 2027");
    expect(formatTrialEnd("not a date", "en")).toBeNull();
  });

  it("shows Free until {date} during the trial", async () => {
    request.mockResolvedValue({
      in_trial: true,
      trial_ends_at: "2027-01-15T09:00:00Z",
    });
    render(<TrialBanner />);
    expect(
      (await screen.findByTestId("vendor-trial-banner")).textContent,
    ).toContain('banner:{"date":"Jan 15, 2027"}');
  });

  it("renders nothing after the trial or when the status fails", async () => {
    request.mockResolvedValue({
      in_trial: false,
      trial_ends_at: "2026-01-01T00:00:00Z",
    });
    const { container } = render(<TrialBanner />);
    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });
});
