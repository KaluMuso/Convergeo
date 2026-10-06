import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import common from "../../../../../../../packages/i18n/messages/en/common.json";
import en from "../../../../../../../packages/i18n/messages/en/vendor.json";

import { buildCanonicalSpec } from "./canonical-details";
import { NewCanonicalForm } from "./new-canonical-form";

const client = {
  suggestProducts: vi.fn(),
  getCanonicalPreview: vi.fn(),
  listCategories: vi.fn().mockResolvedValue([
    {
      id: "category",
      parent_id: null,
      name: "Existing category",
      commission: { key: "standard", rate_bps: 500 },
    },
    {
      id: "child",
      parent_id: "category",
      name: "Child category",
      commission: { key: "standard", rate_bps: 500 },
    },
  ]),
  createListing: vi.fn().mockResolvedValue({
    listing_id: "draft",
    product_id: "pending",
    mode: "new_canonical",
    status: "draft",
    product_status: "pending_moderation",
  }),
};
const labels = {
  ...en.listings.newCanonical,
  fields: { ...en.listings.fields, required: en.listings.errors.required },
  commission: en.listings.commission,
  submitError: en.listings.errors.submitFailed,
  standaloneRequired: en.listings.errors.standalone_required,
  required: en.listings.errors.required,
};
const onError = vi.fn();
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("canonical detail authoring", () => {
  it("preserves entered units/text through serialization, without inventing unknown values", () => {
    const spec = buildCanonicalSpec([
      { name: " dimensions ", value: " 20 × 10 cm " },
      { name: "care", value: "Line one\nLine two" },
      { name: "", value: "" },
    ]);
    expect(JSON.parse(JSON.stringify(spec))).toEqual({
      dimensions: "20 × 10 cm",
      care: "Line one\nLine two",
    });
  });
  it.each([
    [{ name: "weight", value: "" }],
    [{ name: "", value: "10 kg" }],
    [
      { name: "Weight", value: "10 kg" },
      { name: " weight ", value: "11 kg" },
    ],
    [{ name: "x".repeat(81), value: "value" }],
    [{ name: "care", value: "x".repeat(2001) }],
    Array.from({ length: 33 }, (_, i) => ({ name: String(i), value: "text" })),
  ])("rejects incomplete/duplicate/oversized details", (...entries) => {
    expect(buildCanonicalSpec(entries)).toBeNull();
  });
  it("submits brand, description and named specs via the existing moderated creation request", async () => {
    const success = vi.fn();
    render(
      <NextIntlClientProvider locale="en" messages={{ common }}>
        <NewCanonicalForm
          client={client}
          wholesaleEnabled={false}
          onSuccess={success}
          onError={onError}
          labels={labels}
        />
      </NextIntlClientProvider>,
    );
    await screen.findByRole("option", { name: "Existing category" });
    fireEvent.change(screen.getByRole("textbox", { name: labels.nameLabel }), {
      target: { value: "Product supplied by vendor" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: labels.brandLabel }), {
      target: { value: "Known brand" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: labels.categoryLabel }), {
      target: { value: "category" },
    });
    fireEvent.change(screen.getByLabelText(common.categorySelection.subcategory), {
      target: { value: "child" },
    });
    fireEvent.change(screen.getByLabelText(labels.fields.priceLabel), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: labels.details.about }), {
      target: { value: "Supplier description\nCare instructions" },
    });
    fireEvent.click(screen.getByRole("button", { name: labels.details.add }));
    fireEvent.change(screen.getByRole("textbox", { name: `${labels.details.name} 1` }), {
      target: { value: "materials" },
    });
    fireEvent.click(screen.getByRole("button", { name: labels.submit }));
    expect(client.createListing).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(labels.details.invalid);
    fireEvent.change(screen.getByRole("textbox", { name: `${labels.details.value} 1` }), {
      target: { value: "Cotton as labelled" },
    });
    fireEvent.click(screen.getByRole("button", { name: labels.submit }));
    await waitFor(() => expect(client.createListing).toHaveBeenCalled());
    expect(client.createListing.mock.calls[0]?.[0]).toMatchObject({
      mode: "new_canonical",
      category_id: "child",
      brand: "Known brand",
      description: "Supplier description\nCare instructions",
      spec: { materials: "Cotton as labelled" },
    });
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(
        expect.objectContaining({
          status: "draft",
          product_status: "pending_moderation",
        }),
        false,
      ),
    );
  });
});
