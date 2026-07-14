import { createApiClient } from "@vergeo/config";
import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  buildProductJsonLd,
  JsonLdScript,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import { notFound, redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import {
  PdpInteractiveBody,
  type ComparisonListing,
  type ProductListing,
} from "../../_components/pdp/comparison";
import { specRowsFromJson, SpecsTable } from "../../_components/pdp/specs-table";
import { ReviewsSection } from "./_components/reviews-section";

import type { ListingCondition } from "../../_components/pdp/condition-badge";
import type { Metadata } from "next";

export const revalidate = 3600;

const PRODUCT_CACHE_TAG_PREFIX = "product:";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type ProductImage = {
  public_id: string;
  position: number;
  listing_id: string;
};

type VendorLocation = {
  landmark: string;
  lat: number;
  lng: number;
};

type VendorSummary = {
  id: string;
  slug: string;
  display_name: string;
  preferred_badge: boolean;
  rating_avg: number | null;
  rating_count: number;
  location: VendorLocation | null;
};

type Listing = {
  id: string;
  title: string;
  price_ngwee: number;
  condition: ListingCondition;
  stock_mode: "tracked" | "always_available";
  stock_qty: number | null;
  moq: number;
  wholesale: boolean;
  in_stock: boolean;
  vendor: VendorSummary;
  images: ProductImage[];
};

type ProductDetail = {
  id: string;
  name: string;
  slug: string;
  brand: string | null;
  spec: Record<string, unknown>;
  category_id: string;
  images: ProductImage[];
  listings: Listing[];
  listing_count: number;
};

type ComparisonApiListing = {
  id: string;
  price_ngwee: number;
  condition: ListingCondition;
  vendor: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    rating_avg: number | null;
    rating_count: number;
    lat: number | null;
    lng: number | null;
    landmark: string | null;
  };
  delivery_available: boolean;
  pickup_available: boolean;
};

type ComparisonApiResponse = {
  product_id: string;
  product_slug: string;
  listing_count: number;
  listings: ComparisonApiListing[];
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function productCacheTag(slug: string): string {
  return `${PRODUCT_CACHE_TAG_PREFIX}${slug}`;
}

async function getCatalogTranslator(locale: string): Promise<CatalogTranslator> {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "catalog",
  }) as unknown as CatalogTranslator;
}

async function fetchProduct(
  slug: string,
): Promise<{ kind: "product"; data: ProductDetail } | { kind: "redirect"; slug: string } | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/products/${encodeURIComponent(slug)}`, {
      next: {
        revalidate,
        tags: [productCacheTag(slug), "products"],
      },
      redirect: "manual",
    });

    if (response.status === 301) {
      const location = response.headers.get("location");
      if (location) {
        const redirectedSlug = location.replace(/^\/products\//, "").replace(/\/$/, "");
        if (redirectedSlug && redirectedSlug !== slug) {
          return { kind: "redirect", slug: redirectedSlug };
        }
      }
    }

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      return null;
    }

    return { kind: "product", data: (await response.json()) as ProductDetail };
  } catch {
    const client = createApiClient({ baseUrl: getApiBaseUrl() });
    try {
      const data = await client.request<ProductDetail>(`/products/${encodeURIComponent(slug)}`);
      return { kind: "product", data };
    } catch {
      return null;
    }
  }
}

async function fetchComparison(slug: string): Promise<ComparisonApiResponse | null> {
  try {
    const response = await fetch(
      `${getApiBaseUrl()}/products/${encodeURIComponent(slug)}/comparison`,
      {
        next: {
          revalidate,
          tags: [productCacheTag(slug), "products", "comparison"],
        },
      },
    );

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as ComparisonApiResponse;
  } catch {
    const client = createApiClient({ baseUrl: getApiBaseUrl() });
    try {
      return await client.request<ComparisonApiResponse>(
        `/products/${encodeURIComponent(slug)}/comparison`,
      );
    } catch {
      return null;
    }
  }
}

function selectListing(listings: Listing[], listingId?: string): Listing | null {
  if (listings.length === 0) {
    return null;
  }
  if (listingId) {
    const selected = listings.find((listing) => listing.id === listingId);
    if (selected) {
      return selected;
    }
  }
  return listings[0] ?? null;
}

function galleryImages(
  product: ProductDetail,
  selectedListing: Listing | null,
  alt: string,
): Array<{ publicId: string; alt: string }> {
  const source =
    selectedListing && selectedListing.images.length > 0 ? selectedListing.images : product.images;

  return source.map((image) => ({
    publicId: image.public_id,
    alt,
  }));
}

function toProductListings(product: ProductDetail, alt: string): ProductListing[] {
  return product.listings.map((listing) => ({
    id: listing.id,
    title: listing.title,
    priceNgwee: listing.price_ngwee,
    condition: listing.condition,
    stockMode: listing.stock_mode,
    stockQty: listing.stock_qty,
    moq: listing.moq,
    inStock: listing.in_stock,
    vendor: {
      slug: listing.vendor.slug,
      displayName: listing.vendor.display_name,
      preferredBadge: listing.vendor.preferred_badge,
      ratingAvg: listing.vendor.rating_avg,
      ratingCount: listing.vendor.rating_count,
      landmark: listing.vendor.location?.landmark ?? null,
    },
    images: listing.images.map((image) => ({
      publicId: image.public_id,
      alt,
    })),
  }));
}

function toComparisonListings(
  comparison: ComparisonApiResponse | null,
  product: ProductDetail,
): ComparisonListing[] {
  if (comparison) {
    return comparison.listings.map((listing) => ({
      id: listing.id,
      priceNgwee: listing.price_ngwee,
      condition: listing.condition,
      vendor: {
        id: listing.vendor.id,
        slug: listing.vendor.slug,
        displayName: listing.vendor.display_name,
        preferredBadge: listing.vendor.preferred_badge,
        ratingAvg: listing.vendor.rating_avg,
        ratingCount: listing.vendor.rating_count,
        lat: listing.vendor.lat,
        lng: listing.vendor.lng,
        landmark: listing.vendor.landmark,
      },
      deliveryAvailable: listing.delivery_available,
      pickupAvailable: listing.pickup_available,
    }));
  }

  return product.listings.map((listing) => ({
    id: listing.id,
    priceNgwee: listing.price_ngwee,
    condition: listing.condition,
    vendor: {
      id: listing.vendor.id,
      slug: listing.vendor.slug,
      displayName: listing.vendor.display_name,
      preferredBadge: listing.vendor.preferred_badge,
      ratingAvg: listing.vendor.rating_avg,
      ratingCount: listing.vendor.rating_count,
      lat: listing.vendor.location?.lat ?? null,
      lng: listing.vendor.location?.lng ?? null,
      landmark: listing.vendor.location?.landmark ?? null,
    },
    deliveryAvailable: listing.vendor.location !== null,
    pickupAvailable: listing.vendor.location !== null,
  }));
}

function productImageUrls(product: ProductDetail): string[] {
  return resolveCloudinaryImageUrls(product.images.map((image) => image.public_id));
}

function lowestListingPriceNgwee(listings: Listing[]): number | null {
  if (listings.length === 0) {
    return null;
  }
  return listings.reduce(
    (lowest, listing) => Math.min(lowest, listing.price_ngwee),
    listings[0]?.price_ngwee ?? Number.POSITIVE_INFINITY,
  );
}

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
  searchParams: Promise<{ listing?: string }>;
};

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => [{ locale, slug: "itel-a70" }]);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const t = await getCatalogTranslator(locale);
  const result = await fetchProduct(slug);

  if (!result || result.kind === "redirect") {
    return {
      title: t("pdp.meta.notFoundTitle"),
      robots: { index: false, follow: false },
    };
  }

  const product = result.data;
  const description = t("pdp.meta.descriptionFallback", { name: product.name });
  const canonicalPath = buildLocaleCanonical(locale, "p", product.slug);
  const minPrice = lowestListingPriceNgwee(product.listings);
  const ogParams = new URLSearchParams({ name: product.name });
  if (minPrice !== null) {
    ogParams.set("price", formatK(minPrice));
  }
  const ogImagePath = `${buildLocaleCanonical(locale)}/opengraph-image?${ogParams.toString()}`;

  return {
    title: product.name,
    description,
    alternates: buildCanonicalAlternates(locale, "p", product.slug),
    openGraph: {
      title: product.name,
      description,
      type: "website",
      locale,
      url: canonicalPath,
      images: [{ url: ogImagePath }],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function ProductPage({ params, searchParams }: PageProps) {
  const { locale, slug } = await params;
  const { listing: listingId } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const t = await getCatalogTranslator(locale);
  const [result, comparison] = await Promise.all([fetchProduct(slug), fetchComparison(slug)]);

  if (!result) {
    notFound();
  }

  if (result.kind === "redirect") {
    redirect(`/${locale}/p/${result.slug}`);
  }

  const product = result.data;
  const selectedListing = selectListing(product.listings, listingId);
  const singleVendor = product.listing_count === 1;
  const specRows = specRowsFromJson(product.spec);
  const images = galleryImages(product, selectedListing, product.name);
  const jsonLd = buildProductJsonLd({
    name: product.name,
    slug: product.slug,
    locale,
    brand: product.brand,
    description: t("pdp.meta.descriptionFallback", { name: product.name }),
    imageUrls: productImageUrls(product),
    sku: selectedListing?.id,
    offers: product.listings.map((listing) => ({
      priceNgwee: listing.price_ngwee,
      inStock: listing.in_stock,
      sellerName: listing.vendor.display_name,
    })),
  });
  const productListings = toProductListings(product, product.name);
  const comparisonListings = toComparisonListings(comparison, product);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col gap-6 px-4 py-6 motion-rise lg:max-w-6xl">
      <JsonLdScript data={jsonLd} />

      <header className="flex flex-col gap-2">
        {product.brand ? (
          <p className="text-sm font-medium uppercase tracking-wide text-text-2">{product.brand}</p>
        ) : null}
        <h1 className="font-display text-2xl font-semibold text-text">{product.name}</h1>
      </header>

      <PdpInteractiveBody
        locale={locale}
        productImages={images}
        listings={productListings}
        comparisonListings={comparisonListings}
        initialListingId={listingId}
        singleVendor={singleVendor}
        cloudName={process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME}
        galleryLabels={{
          empty: t("pdp.gallery.empty"),
          previous: t("pdp.gallery.previous"),
          next: t("pdp.gallery.next"),
        }}
        buyBoxLabels={{
          priceLabel: t("pdp.buyBox.priceLabel"),
          quantityLabel: t("pdp.buyBox.quantityLabel"),
          decreaseLabel: t("pdp.buyBox.decrease"),
          increaseLabel: t("pdp.buyBox.increase"),
          decreaseSymbol: t("pdp.buyBox.decreaseSymbol"),
          increaseSymbol: t("pdp.buyBox.increaseSymbol"),
          addToCartLabel: t("pdp.buyBox.addToCart"),
          addToCartSoonLabel: t("pdp.buyBox.addToCartSoon"),
          inStockLabel: t("pdp.buyBox.inStock"),
          outOfStockLabel: t("pdp.buyBox.outOfStock"),
          alwaysAvailableLabel: t("pdp.buyBox.alwaysAvailable"),
          singleVendorLabel: t("pdp.buyBox.singleVendor"),
          conditionNewLabel: t("pdp.condition.new"),
          conditionRefurbishedLabel: t("pdp.condition.refurbished"),
        }}
        comparisonLabels={{
          heading: t("comparison.heading"),
          vendorCount: t("comparison.vendorCount"),
          sortLabel: t("comparison.sortLabel"),
          sortPrice: t("comparison.sortPrice"),
          sortDistance: t("comparison.sortDistance"),
          price: t("comparison.price"),
          condition: t("comparison.condition"),
          distance: t("comparison.distance"),
          vendor: t("comparison.vendor"),
          fulfillment: t("comparison.fulfillment"),
          delivery: t("comparison.delivery"),
          pickup: t("comparison.pickup"),
          selectListing: t("comparison.selectListing"),
          selectedListing: t("comparison.selectedListing"),
          preferredBadge: t("comparison.preferredBadge"),
          noReviews: t("comparison.noReviews"),
          rating: t("comparison.rating"),
          conditionNew: t("comparison.conditionNew"),
          conditionRefurbished: t("comparison.conditionRefurbished"),
          usingFallbackLocation: t("comparison.usingFallbackLocation"),
        }}
        vendorLabels={{
          heading: t("pdp.vendor.heading"),
          preferredBadge: t("pdp.vendor.preferredBadge"),
          noReviews: t("pdp.vendor.noReviews"),
          viewStore: t("pdp.vendor.viewStore"),
        }}
      />

      <SpecsTable
        rows={specRows}
        heading={t("pdp.specs.heading")}
        emptyLabel={t("pdp.specs.empty")}
      />

      <ReviewsSection
        locale={locale}
        productId={product.id}
        cloudName={process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME}
        labels={{
          heading: t("reviews.heading"),
          empty: t("reviews.empty"),
          writeCta: t("reviews.writeCta"),
          starsAria: t("reviews.starsAria"),
          photoAlt: t("reviews.photoAlt"),
          vendorReply: t("reviews.vendorReply"),
          galleryPrevious: t("reviews.galleryPrevious"),
          galleryNext: t("reviews.galleryNext"),
          galleryIndicator: t("reviews.galleryIndicator"),
          loadError: t("reviews.loadError"),
          loading: t("reviews.loading"),
          starFilled: t("reviews.starFilled"),
          starEmpty: t("reviews.starEmpty"),
        }}
      />
    </main>
  );
}
