// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";
import { addCartItem } from "../cart/mini-cart-drawer";

import { PdpInteractiveBody, type ProductListing } from "./comparison";
import { type ContactVendorLabels } from "./contact-vendor-button";
import { assertRscSafeGalleryLabels } from "./gallery-labels";
import { GROUPS, VARIANTS } from "./variant-fixtures";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn().mockResolvedValue({ items: [] }),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

vi.mock("./pickup-locations", () => ({
  fetchPickupLocations: vi.fn().mockResolvedValue({ branchTracked: false, locations: [] }),
}));

vi.mock("./contact-vendor-button", () => ({
  ContactVendorButton: () => <button type="button" data-testid="pdp-contact-vendor-cta" />,
}));

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  vi.mocked(addCartItem).mockClear();
});

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

const listing: ProductListing = {
  id: "listing-1",
  title: "Chitenge wrap dress",
  priceNgwee: 20_000,
  condition: "new",
  productClass: "A",
  stockMode: "tracked",
  stockQty: 12,
  moq: 1,
  inStock: true,
  leadTimeDays: null,
  vendorCapacityPerWeek: null,
  images: [{ publicId: "demo/dress-front", alt: "Chitenge wrap dress" }],
  vendor: {
    slug: "demo-vendor",
    displayName: "Demo Vendor",
    preferredBadge: false,
    ratingAvg: null,
    ratingCount: 0,
    landmark: null,
  },
  optionGroups: GROUPS,
  variants: VARIANTS,
};

function renderBody(
  options: {
    locale?: string;
    catalog?: unknown;
    productImages?: Array<{ publicId: string; alt: string }>;
    listingImages?: Array<{ publicId: string; alt: string }>;
    contactVendorEnabled?: boolean;
  } = {},
) {
  const locale = options.locale ?? "en";
  const catalog = options.catalog ?? catalogMessages;
  const galleryLabels = {
    empty: "No images yet",
    previous: "Previous image",
    next: "Next image",
  };
  assertRscSafeGalleryLabels(galleryLabels);

  const activeListing: ProductListing = {
    ...listing,
    images: options.listingImages ?? listing.images,
  };

  return render(
    <NextIntlClientProvider locale={locale} messages={{ catalog }} onError={() => {}}>
      <PdpInteractiveBody
        locale={locale}
        productId="product-1"
        productSlug="tecno-spark-20"
        productImages={options.productImages ?? []}
        listings={[activeListing]}
        comparisonListings={[]}
        initialListingId={activeListing.id}
        singleVendor
        cloudName="test-cloud"
        galleryLabels={galleryLabels}
        buyBoxLabels={{
          priceLabel: "Price",
          quantityLabel: "Quantity",
          buyBoxAriaLabel: "Purchase options",
          decreaseLabel: "Decrease",
          increaseLabel: "Increase",
          decreaseSymbol: "-",
          increaseSymbol: "+",
          addToCartLabel: "Add to cart",
          addingToCartLabel: "Adding…",
          addToCartErrorLabel: "Could not add to cart.",
          inStockLabel: "In stock",
          outOfStockLabel: "Out of stock",
          alwaysAvailableLabel: "Available",
          singleVendorLabel: "Single vendor",
          conditionNewLabel: "New",
          conditionRefurbishedLabel: "Refurbished",
          conditionUsedLabel: "Used",
          conditionAuthenticityLabel: "Condition & Authenticity",
        }}
        pickupLabels={{
          heading: "Choose a pickup branch",
          selectAria: "Pickup branch",
          placeholder: "Select a branch",
          loading: "Loading pickup branches…",
          loadError: "Could not load pickup branches. Try again.",
          unavailable: "No pickup branch is currently available for this item",
        }}
        comparisonLabels={{
          heading: "Compare",
          vendorCount: "{count} vendors",
          sortLabel: "Sort",
          sortPrice: "Price",
          sortDistance: "Distance",
          price: "Price",
          condition: "Condition",
          distance: "Distance",
          vendor: "Vendor",
          fulfillment: "Fulfillment",
          delivery: "Delivery",
          pickup: "Pickup",
          selectListing: "Select",
          selectedListing: "Selected",
          preferredBadge: "Preferred",
          noReviews: "No reviews",
          rating: "Rating",
          conditionNew: "New",
          conditionRefurbished: "Refurbished",
          conditionUsed: "Used",
          usingFallbackLocation: "Using Lusaka CBD",
          lowestPriceBadge: "Lowest price",
        }}
        vendorLabels={{
          heading: "Seller",
          preferredBadge: "Preferred",
          noReviews: "No reviews",
          viewStore: "View store",
        }}
        trustLabels={{
          delivery: "Delivery available",
          pickup: "Pickup available",
          returns: "Returns policy",
          escrow: "Held in escrow until you confirm",
        }}
        wishlistLabels={{
          add: "Save to wishlist",
          remove: "Remove from wishlist",
          saved: "Saved to wishlist",
        }}
        contactVendorEnabled={options.contactVendorEnabled ?? true}
        contactVendorLabels={catalogMessages.pdp.contactVendor as ContactVendorLabels}
        requestQuoteLabels={
          catalogMessages.pdp.requestQuote as import("./request-quote-button").RequestQuoteLabels
        }
        reportListingLabels={{
          cta: catalogMessages.pdp.reportListing.cta,
          heading: catalogMessages.pdp.reportListing.heading,
          reasonLegend: catalogMessages.pdp.reportListing.reasonLegend,
          detailLabel: catalogMessages.pdp.reportListing.detailLabel,
          detailPlaceholder: catalogMessages.pdp.reportListing.detailPlaceholder,
          submit: catalogMessages.pdp.reportListing.submit,
          cancel: catalogMessages.pdp.reportListing.cancel,
          success: catalogMessages.pdp.reportListing.success,
          signedOut: catalogMessages.pdp.reportListing.signedOut,
          error: catalogMessages.pdp.reportListing.error,
          rateLimited: catalogMessages.pdp.reportListing.rateLimited,
          reasons: [
            {
              value: "counterfeit",
              label: catalogMessages.pdp.reportListing.reasons.counterfeit,
            },
            {
              value: "prohibited",
              label: catalogMessages.pdp.reportListing.reasons.prohibited,
            },
            { value: "scam", label: catalogMessages.pdp.reportListing.reasons.scam },
            {
              value: "misleading",
              label: catalogMessages.pdp.reportListing.reasons.misleading,
            },
            { value: "other", label: catalogMessages.pdp.reportListing.reasons.other },
          ],
        }}
        comparePageLabel="Compare sellers"
      />
    </NextIntlClientProvider>,
  );
}

/** The variant picker is a lazy chunk (bundle budget) — wait for it to mount. */
async function renderBodyReady(...args: Parameters<typeof renderBody>) {
  const view = renderBody(...args);
  await screen.findAllByRole("radiogroup");
  return view;
}

describe("PdpInteractiveBody colour/size variants", () => {
  it("renders swatches and size pills as labelled radio groups", async () => {
    await renderBodyReady();
    const colour = screen.getByRole("radiogroup", { name: "Choose Colour" });
    expect(within(colour).getByRole("radio", { name: "Red" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("radiogroup", { name: "Choose Size" })).toBeInTheDocument();
  });

  it("blocks add-to-cart until every option is chosen and highlights what is missing", async () => {
    await renderBodyReady();
    await waitFor(() => expect(screen.getByTestId("pdp-add-to-cart")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("pdp-add-to-cart"));
    expect(addCartItem).not.toHaveBeenCalled();
    expect(screen.getByTestId("pdp-add-to-cart-error")).toHaveTextContent(
      "Choose Colour and Size to add this to your cart",
    );
    expect(screen.getByRole("radiogroup", { name: "Choose Size" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("disables sold-out and unoffered combinations with the reason in their name", async () => {
    await renderBodyReady();
    fireEvent.click(screen.getByRole("radio", { name: "Red" }));
    expect(screen.getByRole("radio", { name: "M (sold out)" })).toBeDisabled();
    expect(
      screen.getByRole("radio", { name: "L (not available with your other choices)" }),
    ).toBeDisabled();
    expect(screen.getByRole("radio", { name: "S" })).not.toBeDisabled();
  });

  it("swaps price and gallery to the chosen variant and adds it to the cart", async () => {
    await renderBodyReady();
    fireEvent.click(screen.getByRole("radio", { name: "Blue" }));
    fireEvent.click(screen.getByRole("radio", { name: "M" }));

    expect(screen.getByRole("radiogroup", { name: "Colour: Blue" })).toBeInTheDocument();
    expect(screen.getByTestId("pdp-price")).toHaveTextContent("K250.00");
    expect(
      screen.getByTestId("gallery-slide-0").querySelector("img")?.getAttribute("src"),
    ).toContain("img/blue");

    await waitFor(() => expect(screen.getByTestId("pdp-add-to-cart")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("pdp-add-to-cart"));
    await waitFor(() => expect(addCartItem).toHaveBeenCalledTimes(1));
    expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, {
      listingVariantId: "blue-m",
    });
  });

  it("supports arrow-key navigation within a group", async () => {
    await renderBodyReady();
    const red = screen.getByRole("radio", { name: "Red" });
    red.focus();
    fireEvent.keyDown(red, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Blue" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("radio", { name: "Blue" }), { key: "ArrowRight" });
    expect(red).toHaveFocus();
  });

  it("opens the zoomable full-screen viewer from the gallery", async () => {
    renderBody();
    fireEvent.click(screen.getByRole("button", { name: "View image full screen" }));
    expect(await screen.findByRole("dialog", { name: "Image viewer" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
