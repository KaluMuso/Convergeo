// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";
import frCatalog from "../../../../../../../packages/i18n/messages/fr/catalog.json";
import zhCatalog from "../../../../../../../packages/i18n/messages/zh/catalog.json";

import { PdpInteractiveBody, type ProductListing } from "./comparison";
import { type ContactVendorLabels } from "./contact-vendor-button";
import { assertRscSafeGalleryLabels } from "./gallery-labels";

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
  title: "Tecno Spark 20",
  priceNgwee: 1_944_065,
  condition: "new",
  productClass: "A",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
  leadTimeDays: null,
  vendorCapacityPerWeek: null,
  images: [{ publicId: "demo/categories/mobile-phones", alt: "Tecno Spark 20" }],
  vendor: {
    slug: "demo-vendor",
    displayName: "Demo Vendor",
    preferredBadge: false,
    ratingAvg: null,
    ratingCount: 0,
    landmark: null,
  },
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

describe("PdpInteractiveBody gallery (digest 1378788464 regression)", () => {
  it("renders a labelled indicator for a single-image product without crashing", () => {
    renderBody({
      listingImages: [{ publicId: "demo/categories/mobile-phones", alt: "Tecno Spark 20" }],
    });

    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 of 1");
    expect(screen.getByRole("img", { name: "Tecno Spark 20" })).toBeInTheDocument();
    expect(screen.queryByTestId("pdp-gallery-empty")).not.toBeInTheDocument();
  });

  it("renders multi-image indicator and advances without blank stage", () => {
    renderBody({
      listingImages: [
        { publicId: "demo/phone-a", alt: "Itel A70 front" },
        { publicId: "demo/phone-b", alt: "Itel A70 back" },
      ],
    });

    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 of 2");
    fireEvent.click(screen.getByRole("button", { name: "Next image" }));
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 2 of 2");
  });

  it("shows a labelled empty-gallery state when no images exist", () => {
    renderBody({ listingImages: [], productImages: [] });

    expect(screen.getByTestId("pdp-gallery-empty")).toHaveTextContent("No images yet");
    expect(screen.queryByTestId("gallery-strip")).not.toBeInTheDocument();
  });

  it("localises the indicator via client catalog messages (fr / zh)", () => {
    const { unmount } = renderBody({
      locale: "fr",
      catalog: frCatalog,
      listingImages: [{ publicId: "demo/phone", alt: "Téléphone" }],
    });
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("Image 1 sur 1");
    unmount();

    renderBody({
      locale: "zh",
      catalog: zhCatalog,
      listingImages: [{ publicId: "demo/phone", alt: "手机" }],
    });
    expect(screen.getByTestId("gallery-indicator")).toHaveTextContent("第 1/1 张图片");
  });

  it("keeps honest escrow trust copy on the buy box panel", () => {
    renderBody();
    expect(screen.getByText("Held in escrow until you confirm")).toBeInTheDocument();
  });
});

describe("PdpInteractiveBody contact vendor gating (BLK-202)", () => {
  it("hides Contact Vendor when capability is unavailable", () => {
    renderBody({ contactVendorEnabled: false });
    expect(screen.queryByTestId("pdp-contact-vendor-cta")).not.toBeInTheDocument();
  });

  it("renders Contact Vendor when capability is available", async () => {
    renderBody({ contactVendorEnabled: true });
    expect(
      await screen.findByTestId("pdp-contact-vendor-cta", {}, { timeout: 5_000 }),
    ).toBeInTheDocument();
  });
});
