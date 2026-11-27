import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));
vi.mock("@vergeo/config", () => ({ createApiClient: () => ({ request }) }));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import { VendorDisputesListView } from "./disputes-list";

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("VendorDisputesListView", () => {
  it("links each dispute with a locale-absolute href", async () => {
    request.mockResolvedValue([
      { id: "dsp-1", order_id: "ord-1", status: "open", created_at: "2026-01-01T00:00:00Z" },
    ]);
    render(<VendorDisputesListView locale="nya" />);
    const link = (await screen.findByText("disputes.list.order")).closest("a");
    expect(link?.getAttribute("href")).toBe("/nya/disputes/dsp-1");
  });
});
