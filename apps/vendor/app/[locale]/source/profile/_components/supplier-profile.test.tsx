import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { SupplierProfile } from "./supplier-profile";

const ROWS = [
  {
    id: "l1",
    title: "Honey",
    status: "active",
    wholesale: false,
    made_in_zambia_status: null,
    made_in_zambia_reference: null,
    made_in_zambia_review_note: null,
  },
  {
    id: "l2",
    title: "Tea",
    status: "active",
    wholesale: false,
    made_in_zambia_status: "rejected",
    made_in_zambia_reference: "ZABS-1",
    made_in_zambia_review_note: "Certificate expired",
  },
  {
    id: "l3",
    title: "Jam",
    status: "active",
    wholesale: false,
    made_in_zambia_status: "approved",
    made_in_zambia_reference: null,
    made_in_zambia_review_note: null,
  },
];

function mockApi() {
  request.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
    if (path === "/vendor/sourcing/profile") return { supplier_types: [] };
    if (path === "/vendor/sourcing/listings") return ROWS;
    if (init?.method === "PUT" && path.endsWith("/made-in-zambia")) {
      const body = JSON.parse(init.body ?? "{}") as {
        claim: boolean;
        reference?: string | null;
      };
      return {
        ...ROWS[0],
        made_in_zambia_status: body.claim ? "claimed" : null,
        made_in_zambia_reference: body.reference ?? null,
      };
    }
    return {};
  });
}

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("SupplierProfile Made in Zambia claims", () => {
  it("files a claim with a reference and shows it as waiting for review", async () => {
    mockApi();
    render(<SupplierProfile locale="en" />);
    await screen.findByTestId("miz-l1");
    fireEvent.change(
      screen.getByLabelText("profile.miz.referenceLabel", {
        selector: "#miz-ref-l1",
      }),
      {
        target: { value: " ZABS-2026-114 " },
      },
    );
    fireEvent.click(screen.getAllByText("profile.miz.send")[0]!);
    await waitFor(() => {
      const put = request.mock.calls.find((call) => call[1]?.method === "PUT");
      expect(put?.[0]).toBe("/vendor/sourcing/listings/l1/made-in-zambia");
      expect(JSON.parse(put?.[1].body)).toEqual({
        claim: true,
        reference: "ZABS-2026-114",
      });
    });
    await screen.findByText(/profile\.miz\.status\.claimed/);
  });

  it("never offers a self-approve control and shows the rejection note", async () => {
    mockApi();
    render(<SupplierProfile locale="en" />);
    await screen.findByTestId("miz-l2");
    expect(screen.getByText(/Certificate expired/)).toBeTruthy();
    expect(screen.getByTestId("miz-l2").textContent).toContain("profile.miz.send"); // can re-claim
    expect(screen.getByTestId("miz-l3").textContent).toContain("profile.miz.status.approved");
    expect(screen.getByTestId("miz-l3").textContent).not.toContain("profile.miz.send");
  });

  it("rejects a too-short reference before calling the API", async () => {
    mockApi();
    render(<SupplierProfile locale="en" />);
    await screen.findByTestId("miz-l1");
    fireEvent.change(
      screen.getByLabelText("profile.miz.referenceLabel", {
        selector: "#miz-ref-l1",
      }),
      {
        target: { value: "ab" },
      },
    );
    fireEvent.click(screen.getAllByText("profile.miz.send")[0]!);
    await screen.findByText("profile.miz.referenceTooShort");
    expect(request.mock.calls.some((call) => call[1]?.method === "PUT")).toBe(false);
  });
});
