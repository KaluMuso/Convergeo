import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { buildCanonicalAlternates } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BackToTop } from "../_components/back-to-top";
import { dealToListing, fetchDeals } from "../_components/deals-data";
import {
  catalogDeliveryLabels,
  catalogMadeToOrderLabels,
} from "../_components/plp/delivery-labels";
import { ListingGrid, type CatalogListing } from "../_components/plp/listing-grid";

import { DealCountdown } from "./_components/deal-countdown";

import type { Metadata } from "next";

export const revalidate = 60;

type PageProps = { params: Promise<{ locale: string }> };

async function getTranslator(locale: string) {
  const base = await getMessages();
  const catalog = await loadNamespace(locale as Locale, "catalog");
  return createTranslator({
    locale,
    messages: { ...base, catalog } as AbstractIntlMessages,
    namespace: "catalog",
  });
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
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
  const [t, data] = await Promise.all([getTranslator(locale), fetchDeals(48)]);
  const items = data?.items ?? [];

  const listings: CatalogListing[] = items.map(dealToListing);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 pb-8">
      <div>
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{t("deals.title")}</h1>
        <p className="m-0 mt-1 text-sm text-text-2">{t("deals.subtitle")}</p>
      </div>

      {data === null ? (
        <EmptyState title={t("deals.unavailable")} />
      ) : items.length === 0 ? (
        <EmptyState
          title={t("deals.emptyTitle")}
          body={t("deals.emptyBody")}
          action={
            <LinkButton href={`/${locale}/c/all`} variant="primary" LinkComponent={Link}>
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
              madeToOrder: catalogMadeToOrderLabels((key) => t.raw(key)),
            }}
          />
          <BackToTop label={t("plp.backToTop")} />
        </>
      )}
    </div>
  );
}
