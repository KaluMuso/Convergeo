import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import common from "../../../../../../../packages/i18n/messages/en/common.json";
import en from "../../../../../../../packages/i18n/messages/en/vendor.json";

import { QuickListForm } from "./quick-list-form";

const client = {
  suggestProducts: vi.fn(),
  getCanonicalPreview: vi.fn(),
  listCategories: vi.fn().mockResolvedValue([{ id: "category", name: "Furniture" }]),
  createListing: vi.fn().mockResolvedValue({ listing_id: "new-listing", status: "draft" }),
};
const onSuccess = vi.fn();
const onError = vi.fn();
const labels = {
  ...en.listings.quickList,
  fields: { ...en.listings.fields, required: en.listings.errors.required },
  submitError: en.listings.errors.submitFailed,
  standaloneRequired: en.listings.errors.standalone_required,
  policyBlocked: en.listings.errors.policyBlocked,
  catalogLabel: en.listings.tabs.attach,
  categoryLabel: en.listings.newCanonical.categoryLabel,
  categoryPlaceholder: en.listings.newCanonical.categoryPlaceholder,
  required: en.listings.errors.required,
};

function mount() {
  render(
    <NextIntlClientProvider locale="en" messages={{ common }}>
      <QuickListForm
        client={client}
        labels={labels}
        wholesaleEnabled={false}
        onSuccess={onSuccess}
        onError={onError}
        onRequestCatalog={vi.fn()}
      />
    </NextIntlClientProvider>,
  );
  fireEvent.change(screen.getByRole("textbox", { name: labels.titleLabel }), {
    target: { value: "Furniture offer" },
  });
  fireEvent.change(screen.getByLabelText(labels.fields.priceLabel), {
    target: { value: "120.00" },
  });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("does not silently change the default Class C or submit a noncanonical quick offer", async () => {
  mount();
  await waitFor(() => expect(client.listCategories).toHaveBeenCalled());
  const productClass = screen.getByLabelText(labels.fields.productClassLabel) as HTMLSelectElement;
  expect(productClass.value).toBe("C");
  // Class C must attach to a canonical product: the draft action stays
  // unavailable and the catalogue path is offered instead.
  const save = screen.getByRole("button", { name: labels.saveDraft }) as HTMLButtonElement;
  expect(save.disabled).toBe(true);
  fireEvent.click(save);
  expect(screen.getByRole("button", { name: labels.catalogLabel })).toBeTruthy();
  expect(client.createListing).not.toHaveBeenCalled();
});

for (const productClass of ["D", "E"]) {
  it(`submits explicitly selected Class ${productClass} with owned category/description as a draft`, async () => {
    mount();
    fireEvent.change(screen.getByLabelText(labels.fields.productClassLabel), {
      target: { value: productClass },
    });
    await screen.findByRole("option", { name: "Furniture" });
    await waitFor(() =>
      expect((screen.getByRole("combobox", { name: labels.categoryLabel }) as HTMLSelectElement).disabled).toBe(false),
    );
    fireEvent.change(screen.getByRole("combobox", { name: labels.categoryLabel }), {
      target: { value: "category" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: labels.descriptionLabel }), {
      target: {
        value: "Detailed furniture offer with dimensions and materials.",
      },
    });
    if (productClass === "D") {
      fireEvent.change(screen.getByLabelText(labels.fields.defectNotesLabel), {
        target: { value: "A visible scratch on the arm." },
      });
    } else {
      fireEvent.change(screen.getByLabelText(labels.fields.leadTimeLabel), {
        target: { value: "21" },
      });
      fireEvent.change(screen.getByLabelText(labels.fields.capacityLabel), {
        target: { value: "3" },
      });
    }
    fireEvent.click(screen.getByRole("button", { name: labels.saveDraft }));
    await waitFor(() => expect(client.createListing).toHaveBeenCalledOnce());
    expect(client.createListing.mock.calls[0]?.[0]).toMatchObject({
      mode: "quick_list",
      product_class: productClass,
      category_id: "category",
      description: "Detailed furniture offer with dimensions and materials.",
      publish: false,
    });
    // Standalone offers never attach a canonical product (absent or null).
    expect(client.createListing.mock.calls[0]?.[0]?.product_id ?? null).toBeNull();
    expect(onError).not.toHaveBeenCalled();
    expect(onSuccess).toHaveBeenCalledOnce();
  });
}
