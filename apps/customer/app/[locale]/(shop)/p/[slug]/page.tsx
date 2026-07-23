import { createApiClient } from "@vergeo/config";
import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import {
  buildBreadcrumbListJsonLd,
  buildCanonicalAlternates,
  buildLocaleCanonical,
  buildProductJsonLd,
  canBuildProductJsonLd,
  JsonLdScript,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import { Tabs } from "@vergeo/ui/src/tabs";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { absoluteApiUrl, getApiBaseUrl } from "../../../../../lib/api-base-url";
import {
  PdpInteractiveBody,
  type ComparisonListing,
  type ProductListing,
} from "../../_components/pdp/comparison";
import {
  fetchProduct,
  productCacheTag,
  type Listing,
  type ProductDetail,
} from "../../_components/pdp/fetch-product";
import { NoSellersPanel } from "../../_components/pdp/no-sellers-panel";
import { ProductViewTracker } from "../../_components/pdp/product-view-tracker";
import { RelatedProducts } from "../../_components/pdp/related-products";
import { specRowsFromJson, SpecsTable } from "../../_components/pdp/specs-table";

import {
  ReviewsSection,
  type ReviewRow,
  type ReviewsSectionLabels,
} from "./_components/reviews-section";

import type { ListingCondition } from "../../_components/pdp/condition-badge";
import type { Metadata } from "next";

// Must be a literal for Next.js segment config (imported constants are rejected).
export const revalidate = 3600;

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
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

async function getNavTranslator(locale: string): Promise<CatalogTranslator> {
  const baseMessages = await getMessages();
  const navMessages = await loadNamespace(locale as Locale, "nav");
  const messages = { ...baseMessages, nav: navMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "nav",
  }) as unknown as CatalogTranslator;
}

async function fetchComparison(slug: string): Promise<ComparisonApiResponse | null> {
  try {
    const url = absoluteApiUrl(`/products/${encodeURIComponent(slug)}/comparison`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: {
        revalidate,
        tags: [productCacheTag(slug), "products", "comparison"],
      },
    });

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

type RelatedProduct = {
  slug: string;
  name: string;
  image_public_id: string | null;
  from_price_ngwee: number | null;
};

type RelatedApiResponse = {
  product_slug: string;
  items: RelatedProduct[];
};

async function fetchRelated(slug: string): Promise<RelatedProduct[]> {
  try {
    const url = absoluteApiUrl(`/products/${encodeURIComponent(slug)}/related`);
    if (!url) {
      return [];
    }
    const response = await fetch(url, {
      next: {
        revalidate,
        tags: [productCacheTag(slug), "products", "related"],
      },
    });
    if (!response.ok) {
      return [];
    }
    const data = (await response.json()) as RelatedApiResponse;
    return data.items ?? [];
  } catch {
    return [];
  }
}

async function fetchReviews(productId: string): Promise<ReviewRow[] | null> {
  try {
    const url = absoluteApiUrl(`/reviews?product_id=${encodeURIComponent(productId)}`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: {
        revalidate,
        tags: ["reviews", `reviews:${productId}`],
      },
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as ReviewRow[];
  } catch {
    return null;
  }
}

/**
 * Reviews are below the fold and the PDP renders dynamically (reads searchParams),
 * so this is isolated in a Suspense boundary — the review fetch streams in instead
 * of blocking the document's TTFB. Fails silent: the section is omitted on error.
 */
async function ReviewsPanel({
  locale,
  productId,
  cloudName,
  labels,
}: {
  locale: string;
  productId: string;
  cloudName?: string;
  labels: ReviewsSectionLabels;
}) {
  const reviews = await fetchReviews(productId);
  if (!reviews) {
    return null;
  }
  return <ReviewsSection locale={locale} reviews={reviews} cloudName={cloudName} labels={labels} />;
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

function descriptionParagraphs(description: string | null): string[] {
  if (!description) {
    return [];
  }
  return description
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph.length > 0);
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

  if (result.kind !== "product") {
    return {
      title:
        result.kind === "unavailable" ? t("pdp.unavailableTitle") : t("pdp.meta.notFoundTitle"),
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

  const indexable = product.listings.length > 0;

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
      index: indexable,
      follow: indexable,
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
  const tNav = await getNavTranslator(locale);
  const result = await fetchProduct(slug);

  if (result.kind === "redirect") {
    redirect(`/${locale}/p/${result.slug}`);
  }

  if (result.kind === "not_found") {
    notFound();
  }

  if (result.kind === "unavailable") {
    const retryHref = `/${locale}/p/${encodeURIComponent(slug)}`;
    return (
      <div className="mx-auto w-full max-w-3xl py-10">
        <EmptyState
          title={t("pdp.unavailableTitle")}
          body={t("pdp.unavailableBody")}
          data-testid="pdp-unavailable"
          action={
            <Link
              href={retryHref}
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)]"
            >
              {t("pdp.unavailableRetry")}
            </Link>
          }
        />
      </div>
    );
  }

  const [comparison, related] = await Promise.all([fetchComparison(slug), fetchRelated(slug)]);

  const product = result.data;
  const selectedListing = selectListing(product.listings, listingId);
  const singleVendor = product.listing_count === 1;
  const specRows = specRowsFromJson(product.spec);
  const images = galleryImages(product, selectedListing, product.name);
  const productJsonLdInput = {
    name: product.name,
    slug: product.slug,
    locale,
    brand: product.brand,
    description: product.description?.trim() || undefined,
    imageUrls: productImageUrls(product),
    offers: product.listings.map((listing) => ({
      priceNgwee: listing.price_ngwee,
      inStock: listing.in_stock,
      sellerName: listing.vendor.display_name,
    })),
  };
  const productJsonLd = canBuildProductJsonLd(productJsonLdInput)
    ? buildProductJsonLd(productJsonLdInput)
    : null;
  const breadcrumbJsonLd = buildBreadcrumbListJsonLd(locale, [
    { name: tNav("shop.home"), path: "" },
    { name: product.name, path: `p/${product.slug}` },
  ]);
  const productListings = toProductListings(product, product.name);
  const comparisonListings = toComparisonListings(comparison, product);
  const overviewParagraphs = descriptionParagraphs(product.description);

  const reviewsPanel = (
    <Suspense fallback={null}>
      <ReviewsPanel
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
          starFilled: t("reviews.starFilled"),
          starEmpty: t("reviews.starEmpty"),
          distributionHeading: t("reviews.distributionHeading"),
          distributionRowAria: t("reviews.distributionRowAria"),
          report: {
            cta: t("reviews.report.cta"),
            heading: t("reviews.report.heading"),
            reasonLegend: t("reviews.report.reasonLegend"),
            submit: t("reviews.report.submit"),
            cancel: t("reviews.report.cancel"),
            success: t("reviews.report.success"),
            signedOut: t("reviews.report.signedOut"),
            error: t("reviews.report.error"),
            reasons: [
              { value: "spam", label: t("reviews.report.reasons.spam") },
              { value: "abuse", label: t("reviews.report.reasons.abuse") },
              { value: "private_info", label: t("reviews.report.reasons.privateInfo") },
              { value: "not_relevant", label: t("reviews.report.reasons.notRelevant") },
            ],
          },
        }}
      />
    </Suspense>
  );

  const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
  const hasOffers = productListings.length > 0;
  const relatedCardLabels = {
    heading: t("pdp.related.heading"),
    vendorFallback: t("pdp.related.vendorFallback"),
    noReviews: t("plp.card.noReviews"),
    reviewCount: t("plp.card.reviewCount"),
    quickAdd: t("plp.card.quickAdd"),
    wishlist: t("plp.card.wishlist"),
    mediaEmpty: t("pdp.gallery.empty"),
  };

  return (
    // Shop layout already provides the page <main> landmark — avoid nesting.
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6 py-6 motion-rise lg:max-w-6xl">
      {productJsonLd ? <JsonLdScript data={productJsonLd} /> : null}
      <JsonLdScript data={breadcrumbJsonLd} />
      <ProductViewTracker
        productId={product.id}
        listingId={selectedListing?.id}
        recent={{
          slug: product.slug,
          name: product.name,
        }}
      />

      <nav aria-label={t("pdp.breadcrumbAria")} className="text-sm text-text-2">
        <ol className="m-0 flex list-none flex-wrap items-center gap-1 p-0">
          <li className="flex min-w-0 items-center gap-1">
            <Link
              href={`/${locale}`}
              className="truncate text-primary hover:underline focus-visible:outline-none"
            >
              {tNav("shop.home")}
            </Link>
            <span className="shrink-0 text-text-3 before:content-['/']" aria-hidden />
          </li>
          <li className="flex min-w-0 items-center gap-1">
            <span className="truncate font-medium text-text" aria-current="page">
              {product.name}
            </span>
          </li>
        </ol>
      </nav>

      <header className="flex flex-col gap-2" data-testid="pdp-header">
        {product.brand ? (
          <p className="text-sm font-medium uppercase tracking-wide text-text-2">{product.brand}</p>
        ) : null}
        <h1 className="font-display text-2xl font-semibold text-text lg:text-3xl">
          {product.name}
        </h1>
        {product.listing_count > 0 ? (
          <p className="text-sm text-text-2" data-testid="pdp-seller-count">
            {t("pdp.sellerCount", { count: product.listing_count })}
          </p>
        ) : null}
        {product.listing_count > 1 ? (
          <Link
            href={`/${locale}/compare?product=${encodeURIComponent(product.slug)}`}
            className="inline-flex min-h-11 w-fit items-center text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            data-testid="pdp-compare-entry"
          >
            {t("comparePage.entryCta")}
          </Link>
        ) : null}
      </header>

      {hasOffers ? (
        <PdpInteractiveBody
          locale={locale}
          productId={product.id}
          productSlug={product.slug}
          productImages={images}
          listings={productListings}
          comparisonListings={comparisonListings}
          initialListingId={listingId}
          singleVendor={singleVendor}
          cloudName={cloudName}
          galleryLabels={{
            // Strings only — indicator text is formatted inside the client body
            // (passing a function here caused live digest 1378788464).
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
            addingToCartLabel: t("pdp.buyBox.addingToCart"),
            addToCartErrorLabel: t("pdp.buyBox.addToCartError"),
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
            lowestPriceBadge: t("comparison.lowestPriceBadge"),
          }}
          vendorLabels={{
            heading: t("pdp.vendor.heading"),
            preferredBadge: t("pdp.vendor.preferredBadge"),
            noReviews: t("pdp.vendor.noReviews"),
            viewStore: t("pdp.vendor.viewStore"),
          }}
          trustLabels={{
            delivery: t("pdp.trust.delivery"),
            pickup: t("pdp.trust.pickup"),
            returns: t("pdp.trust.returns"),
            escrow: t("pdp.trust.escrow"),
          }}
          wishlistLabels={{
            add: t("pdp.buyBox.wishlistAdd"),
            remove: t("pdp.buyBox.wishlistRemove"),
            saved: t("pdp.buyBox.wishlistSaved"),
          }}
          comparePageLabel={t("comparePage.entryCta")}
        />
      ) : (
        <NoSellersPanel
          title={t("pdp.noSellers.title")}
          body={t("pdp.noSellers.body")}
          browseLabel={t("pdp.noSellers.browseCta")}
          browseHref={`/${locale}/c/all`}
        />
      )}

      <Tabs
        ariaLabel={t("pdp.tabs.ariaLabel")}
        mountInactivePanels
        items={[
          ...(overviewParagraphs.length > 0
            ? [
                {
                  key: "overview",
                  label: t("pdp.tabs.overview"),
                  panel: (
                    <section className="flex flex-col gap-3">
                      <h2 className="font-display text-lg font-semibold text-text">
                        {t("pdp.overview.heading")}
                      </h2>
                      <div className="flex flex-col gap-2 text-sm leading-relaxed text-text-2">
                        {overviewParagraphs.map((paragraph, index) => (
                          <p key={index}>{paragraph}</p>
                        ))}
                      </div>
                    </section>
                  ),
                },
              ]
            : []),
          {
            key: "specs",
            label: t("pdp.tabs.specs"),
            panel: (
              <SpecsTable
                rows={specRows}
                heading={t("pdp.specs.heading")}
                emptyLabel={t("pdp.specs.empty")}
              />
            ),
          },
          {
            key: "reviews",
            label: t("pdp.tabs.reviews"),
            panel: reviewsPanel,
          },
        ]}
      />

      <RelatedProducts
        locale={locale}
        items={related}
        labels={relatedCardLabels}
        cloudName={cloudName}
      />
    </div>
  );
}
