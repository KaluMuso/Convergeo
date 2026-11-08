import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));

import { VariantsEditor } from "./variants-editor";

import type { ListingVariantsResponse } from "../[id]/edit/_lib/manage-client";

afterEach(() => cleanup());

const existing: ListingVariantsResponse = {
  listing_id: "listing-1",
  listing_price_ngwee: 20_000,
  stock_mode: "tracked",
  groups: [
    {
      id: "g1",
      name: "Colour",
      display: "swatch",
      values: [
        { id: "v1", label: "Red", swatch_hex: "#C0392B" },
        { id: "v2", label: "Blue", swatch_hex: null },
      ],
    },
  ],
  variants: [
    {
      id: "x1",
      options: ["Red"],
      sku: "R",
      stock_qty: 4,
      price_ngwee: 25_000,
      compare_at_ngwee: null,
      image_public_id: null,
      status: "active",
    },
  ],
};

function client(response: ListingVariantsResponse = existing) {
  return {
    getVariants: vi.fn().mockResolvedValue(response),
    replaceVariants: vi.fn().mockResolvedValue(response),
  };
}

function renderEditor(api = client()) {
  render(
    <VariantsEditor
      listingId="listing-1"
      client={api}
      imagePublicIds={["img/1"]}
      stockTracked
      listingPriceNgwee={20_000}
    />,
  );
  return api;
}

describe("VariantsEditor", () => {
  it("loads existing options into the matrix with kwacha prices", async () => {
    renderEditor();
    expect(await screen.findByTestId("variants-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("variants-row-0")).toHaveTextContent("Red");
    expect(screen.getByDisplayValue("250.00")).toBeInTheDocument();
    expect(screen.getByTestId("variants-row-1")).toHaveTextContent("Blue");
  });

  it("blocks saving and points at the field when stock is missing", async () => {
    const api = renderEditor();
    await screen.findByTestId("variants-matrix");
    fireEvent.click(screen.getByTestId("variants-save"));
    expect(api.replaceVariants).not.toHaveBeenCalled();
    expect(screen.getByTestId("variants-status")).toHaveTextContent("listings.variants.fixErrors");
    expect(screen.getByText(/listings\.variants\.errors\.stockRequired/)).toBeInTheDocument();
  });

  it("adds a Size option, keeps the draft across re-renders and saves the new matrix", async () => {
    const api = renderEditor();
    await screen.findByTestId("variants-matrix");
    fireEvent.click(screen.getByTestId("variants-add-group"));
    fireEvent.change(screen.getByTestId("variants-group-name-1"), { target: { value: "Size" } });
    fireEvent.change(screen.getByTestId("variants-value-1-0"), { target: { value: "M" } });
    await waitFor(() => expect(screen.getByTestId("variants-row-1")).toHaveTextContent("Blue / M"));
    fireEvent.change(screen.getByTestId("variants-stock-0"), { target: { value: "3" } });
    fireEvent.change(screen.getByTestId("variants-stock-1"), { target: { value: "5" } });
    fireEvent.click(screen.getByTestId("variants-save"));

    await waitFor(() => expect(api.replaceVariants).toHaveBeenCalledTimes(1));
    const [, payload] = api.replaceVariants.mock.calls[0] as [
      string,
      ReturnType<typeof JSON.parse>,
    ];
    expect(payload.groups.map((g: { name: string }) => g.name)).toEqual(["Colour", "Size"]);
    // A new combination starts without a price override (inherits the listing price).
    expect(payload.variants[0]).toMatchObject({
      options: ["Red", "M"],
      stock_qty: 3,
      price_ngwee: null,
    });
    expect(payload.variants[1]).toMatchObject({ options: ["Blue", "M"], price_ngwee: null });
  });

  it("explains why a listing kind cannot have options", () => {
    render(
      <VariantsEditor
        listingId="listing-1"
        client={client()}
        imagePublicIds={[]}
        stockTracked
        listingPriceNgwee={20_000}
        unsupportedReason="wholesale"
      />,
    );
    expect(screen.getByRole("note")).toHaveTextContent("listings.variants.unsupported.wholesale");
  });
});
