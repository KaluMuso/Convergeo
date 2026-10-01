import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ImportFlow } from "./import-flow";

const mocks = vi.hoisted(() => ({
  translate: Object.assign((key: string) => key, { has: () => true }),
  session: { access_token: "test-token", user: { id: "owner" } },
  preview: vi.fn(),
  apply: vi.fn(),
  template: vi.fn(),
}));
vi.mock("next-intl", () => ({ useTranslations: () => mocks.translate }));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: mocks.session, loading: false }),
}));
vi.mock("../_lib/import-client", () => ({
  previewCsv: mocks.preview,
  applyRawRows: mocks.apply,
  downloadTemplateCsv: mocks.template,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("mounts preview/apply and displays the server's preserved-stock outcome", async () => {
  const raw = {
    sku: "RICE",
    title: "Rice",
    price_ngwee: "12000",
    stock_qty: "10",
    stock_mode: "tracked",
    product_id: "product",
  };
  mocks.preview.mockResolvedValue({
    total: 1,
    valid: 1,
    invalid: 0,
    rows: [
      {
        row: 1,
        ok: true,
        errors: [],
        sku: "RICE",
        title: "Rice",
        price_ngwee: 12000,
        product_id: "product",
        matched_name: "Rice",
        suggestions: [],
        raw,
      },
    ],
  });
  mocks.apply.mockResolvedValue({
    accepted: 1,
    rejected: 0,
    rows: [{ row: 1, ok: true, errors: [], listing_id: "listing", stock_preserved: true }],
  });
  render(<ImportFlow />);
  fireEvent.change(screen.getByLabelText("listings.import.upload.fileLabel"), {
    target: { files: [new File(["csv"], "stock.csv", { type: "text/csv" })] },
  });
  fireEvent.click(screen.getByRole("button", { name: "listings.import.preview.previewButton" }));
  fireEvent.click(await screen.findByRole("button", { name: "listings.import.apply.button" }));
  await screen.findByText("listings.import.results.stockPreserved");
  expect(mocks.apply.mock.calls[0]?.[0]).toEqual([raw]);
});

it("shows a localized template failure instead of reporting success", async () => {
  mocks.template.mockRejectedValue(new Error("network"));
  render(<ImportFlow />);
  fireEvent.click(screen.getByRole("button", { name: "listings.import.template.download" }));
  await screen.findByText("listings.import.errors.templateFailed");
  expect(mocks.template).toHaveBeenCalledOnce();
});
