import { createApiClient } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound, redirect } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BuyBox, type BuyBoxListing } from "../../_components/pdp/buy-box";
import { PdpGallery } from "../../_components/pdp/gallery";
import { specRowsFromJson, SpecsTable } from "../../_components/pdp/specs-table";
import { VendorBlock } from "../../_components/pdp/vendor-block";

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

function buildProductJsonLd(product: ProductDetail, selectedListing: Listing | null) {
  const offers = product.listings.map((listing) => ({
    "@type": "Offer",
    priceCurrency: "ZMW",
    price: (listing.price_ngwee / 100).toFixed(2),
    availability: listing.in_stock ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
    seller: {
      "@type": "Organization",
      name: listing.vendor.display_name,
    },
  }));

  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined,
    offers: offers.length === 1 ? offers[0] : offers,
    image: product.images.map((image) => image.public_id),
    sku: selectedListing?.id,
  };
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

  return {
    title: product.name,
    description,
    alternates: {
      canonical: `/${locale}/p/${product.slug}`,
    },
    openGraph: {
      title: product.name,
      description,
      type: "website",
      locale,
      url: `/${locale}/p/${product.slug}`,
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
  const result = await fetchProduct(slug);

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
  const jsonLd = buildProductJsonLd(product, selectedListing);

  const buyBoxListing: BuyBoxListing | null = selectedListing
    ? {
        id: selectedListing.id,
        title: selectedListing.title,
        priceNgwee: selectedListing.price_ngwee,
        condition: selectedListing.condition,
        stockMode: selectedListing.stock_mode,
        stockQty: selectedListing.stock_qty,
        moq: selectedListing.moq,
        inStock: selectedListing.in_stock,
      }
    : null;

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col gap-6 px-4 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <header className="flex flex-col gap-2">
        {product.brand ? (
          <p className="text-sm font-medium uppercase tracking-wide text-text-2">{product.brand}</p>
        ) : null}
        <h1 className="font-display text-2xl font-semibold text-text">{product.name}</h1>
      </header>

      <PdpGallery
        images={images}
        cloudName={process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME}
        emptyLabel={t("pdp.gallery.empty")}
        indicatorLabel={(current, total) => t("pdp.gallery.indicator", { current, total })}
        previousLabel={t("pdp.gallery.previous")}
        nextLabel={t("pdp.gallery.next")}
      />

      {buyBoxListing ? (
        <BuyBox
          listing={buyBoxListing}
          singleVendor={singleVendor}
          labels={{
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
            lowStockLabel: (count) => t("pdp.buyBox.lowStock", { count }),
            alwaysAvailableLabel: t("pdp.buyBox.alwaysAvailable"),
            singleVendorLabel: t("pdp.buyBox.singleVendor"),
            moqLabel: (count) => t("pdp.buyBox.moq", { count }),
            conditionNewLabel: t("pdp.condition.new"),
            conditionRefurbishedLabel: t("pdp.condition.refurbished"),
          }}
        />
      ) : null}

      {selectedListing ? (
        <VendorBlock
          locale={locale}
          vendor={{
            slug: selectedListing.vendor.slug,
            displayName: selectedListing.vendor.display_name,
            preferredBadge: selectedListing.vendor.preferred_badge,
            ratingAvg: selectedListing.vendor.rating_avg,
            ratingCount: selectedListing.vendor.rating_count,
            landmark: selectedListing.vendor.location?.landmark ?? null,
          }}
          heading={t("pdp.vendor.heading")}
          preferredBadgeLabel={t("pdp.vendor.preferredBadge")}
          noReviewsLabel={t("pdp.vendor.noReviews")}
          ratingLabel={
            selectedListing.vendor.rating_avg !== null && selectedListing.vendor.rating_count > 0
              ? t("pdp.vendor.rating", {
                  rating: selectedListing.vendor.rating_avg,
                  count: selectedListing.vendor.rating_count,
                })
              : t("pdp.vendor.noReviews")
          }
          viewStoreLabel={t("pdp.vendor.viewStore")}
        />
      ) : null}

      <SpecsTable
        rows={specRows}
        heading={t("pdp.specs.heading")}
        emptyLabel={t("pdp.specs.empty")}
      />
    </main>
  );
}
