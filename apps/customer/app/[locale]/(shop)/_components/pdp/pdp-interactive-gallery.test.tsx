// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";
import frCatalog from "../../../../../../../packages/i18n/messages/fr/catalog.json";
import zhCatalog from "../../../../../../../packages/i18n/messages/zh/catalog.json";

import { PdpInteractiveBody, type ProductListing } from "./comparison";
import { assertRscSafeGalleryLabels } from "./gallery-labels";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn().mockResolvedValue({ items: [] }),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

afterEach(() => {
  cleanup();
});

const listing: ProductListing = {
  id: "listing-1",
  title: "Tecno Spark 20",
  priceNgwee: 1_944_065,
  condition: "new",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
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
          usingFallbackLocation: "Using Lusaka CBD",
        }}
        vendorLabels={{
          heading: "Seller",
          preferredBadge: "Preferred",
          noReviews: "No reviews",
          viewStore: "View store",
        }}
        trustLabels={{
          preferredSeller: "Preferred seller: {name}",
          seller: "Seller: {name}",
          delivery: "Delivery available",
          pickup: "Pickup available",
          returns: "Returns policy",
          escrow: "Held in escrow until you confirm",
        }}
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
