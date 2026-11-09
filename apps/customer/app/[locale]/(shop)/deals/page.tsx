import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { buildCanonicalAlternates } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { catalogDeliveryLabels } from "../_components/plp/delivery-labels";
import {
  ListingGrid,
  type CatalogListing,
} from "../_components/plp/listing-grid";

import { DealCountdown } from "./_components/deal-countdown";

import type { Metadata } from "next";

export const revalidate = 60;

type DealItem = {
  deal_id: string;
  starts_at: string;
  ends_at: string;
  deal_price_ngwee: number;
  reference_price_ngwee: number;
  discount_percent: number;
  listing: {
    id: string;
    title: string;
    product_slug: string | null;
    vendor_name: string;
    price_ngwee: number;
    condition: string;
    in_stock: boolean;
    image_public_id: string | null;
    rating: number;
    review_count: number;
    distance_m: number | null;
    delivery_available?: boolean;
    pickup_available?: boolean;
  };
};

type DealsResponse = { server_time: string; items: DealItem[] };

type PageProps = { params: Promise<{ locale: string }> };

async function fetchDeals(): Promise<DealsResponse | null> {
  const url = absoluteApiUrl("/deals?limit=48");
  if (!url) {
    return null;
  }
  try {
    const response = await fetch(url, {
      next: { revalidate, tags: ["deals"] },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as DealsResponse;
  } catch {
    return null;
  }
}

async function getTranslator(locale: string) {
  const base = await getMessages();
  const catalog = await loadNamespace(locale as Locale, "catalog");
  return createTranslator({
    locale,
    messages: { ...base, catalog } as AbstractIntlMessages,
    namespace: "catalog",
  });
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslator(locale);
  return {
    title: t("deals.metaTitle"),
    description: t("deals.subtitle"),
    alternates: buildCanonicalAlternates(locale, "deals"),
  };
}

/** Flash deals (GET /deals): image-led grid, live countdown per deal. */
export default async function DealsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }
  setRequestLocale(locale);
  const [t, data] = await Promise.all([getTranslator(locale), fetchDeals()]);
  const items = data?.items ?? [];

  const listings: CatalogListing[] = items.map((deal) => ({
    id: deal.listing.id,
    title: deal.listing.title,
    productSlug: deal.listing.product_slug,
    vendorName: deal.listing.vendor_name,
    priceNgwee: deal.deal_price_ngwee,
    oldNgwee: deal.reference_price_ngwee,
    condition: deal.listing.condition,
    inStock: deal.listing.in_stock,
    imagePublicId: deal.listing.image_public_id,
    rating: deal.listing.rating,
    reviewCount: deal.listing.review_count,
    distanceM: deal.listing.distance_m,
    belowMedian: false,
    deliveryAvailable: deal.listing.delivery_available ?? false,
    pickupAvailable: deal.listing.pickup_available ?? false,
  }));

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 pb-8">
      <div>
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">
          {t("deals.title")}
        </h1>
        <p className="m-0 mt-1 text-sm text-text-2">{t("deals.subtitle")}</p>
      </div>

      {data === null ? (
        <EmptyState title={t("deals.unavailable")} />
      ) : items.length === 0 ? (
        <EmptyState
          title={t("deals.emptyTitle")}
          body={t("deals.emptyBody")}
          action={
            <LinkButton
              href={`/${locale}/c/all`}
              variant="primary"
              LinkComponent={Link}
            >
              {t("deals.browse")}
            </LinkButton>
          }
        />
      ) : (
        <>
          {/* The soonest-ending deal sets the urgency clock for the page. */}
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-hidden>
            {[...items]
              .sort((a, b) => a.ends_at.localeCompare(b.ends_at))
              .slice(0, 1)
              .map((deal) => (
                <li key={deal.deal_id}>
                  <DealCountdown
                    endsAt={deal.ends_at}
                    serverTime={data.server_time}
                    template={t.raw("deals.endsIn") as string}
                    endedLabel={t("deals.ended")}
                  />
                </li>
              ))}
          </ul>
          <ListingGrid
            locale={locale}
            listings={listings}
            labels={{
              vendor: t.raw("plp.card.vendor") as string,
              noReviews: t("plp.card.noReviews"),
              reviewCount: t.raw("plp.card.reviewCount") as string,
              quickAdd: t("plp.card.quickAdd"),
              wishlist: t("plp.card.wishlist"),
              outOfStock: t("plp.card.outOfStock"),
              discount: t.raw("plp.card.discount") as string,
              delivery: catalogDeliveryLabels((key) => t.raw(key)),
            }}
          />
        </>
      )}
    </div>
  );
}
