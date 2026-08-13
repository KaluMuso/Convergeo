import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import {
  buildBreadcrumbListJsonLd,
  buildCanonicalAlternates,
  buildLocaleCanonical,
  JsonLdScript,
} from "@vergeo/ui/src/seo/json-ld";
import { buildSocialMetadata } from "@vergeo/ui/src/seo/metadata";
import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { formatListingQuantity, type SaleUnitLabels } from "../../_components/sale-quantity";
import {
  fetchStandaloneListing,
  type StandaloneListing,
} from "../../_components/standalone-listing/fetch-listing";
import { StandaloneListingBody } from "../../_components/standalone-listing/standalone-listing-body";

import type { BuyBoxLabels, BuyBoxListing } from "../../_components/pdp/buy-box";
import type { Metadata } from "next";

export const revalidate = 60;

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getTranslator(locale: string, namespace: "catalog" | "nav") {
  const baseMessages = await getMessages();
  const namespaceMessages = await loadNamespace(locale as Locale, namespace);
  const messages = { ...baseMessages, [namespace]: namespaceMessages } as AbstractIntlMessages;
  return createTranslator({ locale, messages, namespace }) as unknown as CatalogTranslator;
}

async function getOptionalAccessToken(): Promise<string | null> {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

function unitLabels(t: CatalogTranslator): SaleUnitLabels {
  return {
    each: t("pdp.buyBox.units.each"),
    metre: t("pdp.buyBox.units.metre"),
    kg: t("pdp.buyBox.units.kg"),
    litre: t("pdp.buyBox.units.litre"),
    bag: t("pdp.buyBox.units.bag"),
    sqm: t("pdp.buyBox.units.sqm"),
  };
}

function toBuyBoxListing(listing: StandaloneListing): BuyBoxListing {
  return {
    id: listing.id,
    title: listing.title,
    priceNgwee: listing.price_ngwee,
    condition: listing.condition,
    productClass: listing.product_class,
    stockMode: listing.stock_mode,
    stockQty: listing.stock_qty,
    moq: listing.moq,
    inStock: listing.in_stock,
    saleUnit: listing.sale_unit,
    unitStepMilli: listing.unit_step_milli,
    minSteps: listing.min_steps,
    leadTimeDays: listing.lead_time_days,
    vendorCapacityPerWeek: listing.vendor_capacity_per_week,
  };
}

function buyBoxLabels(t: CatalogTranslator): BuyBoxLabels {
  return {
    priceLabel: t("pdp.buyBox.priceLabel"),
    quantityLabel: t("pdp.buyBox.quantityLabel"),
    buyBoxAriaLabel: t("pdp.buyBox.ariaLabel"),
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
    conditionUsedLabel: t("pdp.condition.used"),
    conditionAuthenticityLabel: t("pdp.condition.authenticity"),
  };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, id } = await params;
  const [t, accessToken] = await Promise.all([
    getTranslator(locale, "catalog"),
    getOptionalAccessToken(),
  ]);
  const result = await fetchStandaloneListing(id, accessToken);

  if (result.kind !== "listing") {
    return {
      title:
        result.kind === "unavailable" ? t("pdp.unavailableTitle") : t("pdp.meta.notFoundTitle"),
      robots: { index: false, follow: false },
    };
  }

  const listing = result.data;
  const description = t("pdp.meta.descriptionFallback", { name: listing.title });
  const canonicalPath = buildLocaleCanonical(locale, "l", listing.id);

  return {
    title: listing.title,
    description,
    alternates: buildCanonicalAlternates(locale, "l", listing.id),
    ...buildSocialMetadata({
      title: listing.title,
      description,
      locale,
      url: canonicalPath,
    }),
    robots: { index: true, follow: true },
  };
}

export default async function StandaloneListingPage({ params }: PageProps) {
  const { locale, id } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const [t, tNav, accessToken] = await Promise.all([
    getTranslator(locale, "catalog"),
    getTranslator(locale, "nav"),
    getOptionalAccessToken(),
  ]);
  const result = await fetchStandaloneListing(id, accessToken);

  if (result.kind === "not_found") {
    notFound();
  }
  if (result.kind === "unavailable") {
    return (
      <div className="mx-auto w-full max-w-3xl py-10">
        <EmptyState
          title={t("pdp.unavailableTitle")}
          body={t("pdp.unavailableBody")}
          data-testid="standalone-listing-unavailable"
          action={
            <LinkButton
              href={`/${locale}/l/${encodeURIComponent(id)}`}
              variant="primary"
              className="rounded-lg text-sm"
              LinkComponent={Link}
            >
              {t("pdp.unavailableRetry")}
            </LinkButton>
          }
        />
      </div>
    );
  }

  const listing = result.data;
  const labels = unitLabels(t);
  const increment = formatListingQuantity(
    1,
    listing.sale_unit,
    listing.unit_step_milli,
    locale,
    labels,
  );
  const minimum = formatListingQuantity(
    Math.max(1, listing.min_steps, listing.moq),
    listing.sale_unit,
    listing.unit_step_milli,
    locale,
    labels,
  );
  const fulfilment =
    listing.fulfilment_mode === "made_to_order"
      ? t("pdp.standalone.fulfilmentMadeToOrder")
      : t("pdp.standalone.fulfilmentStocked");
  const images = [...listing.images]
    .sort((left, right) => left.position - right.position)
    .map((image) => ({ publicId: image.cloudinary_public_id, alt: listing.title }));
  const breadcrumbJsonLd = buildBreadcrumbListJsonLd(locale, [
    { name: tNav("shop.home"), path: "" },
    { name: listing.title, path: `l/${listing.id}` },
  ]);

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6 py-6 motion-rise lg:max-w-6xl">
      <JsonLdScript data={breadcrumbJsonLd} />

      <nav aria-label={t("pdp.breadcrumbAria")} className="text-sm text-text-2">
        <ol className="m-0 flex list-none flex-wrap items-center gap-1 p-0">
          <li className="flex min-w-0 items-center gap-1">
            <Link
              href={`/${locale}`}
              className="truncate text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {tNav("shop.home")}
            </Link>
            <span className="shrink-0 text-text-3 before:content-['/']" aria-hidden />
          </li>
          <li className="min-w-0">
            <span className="block truncate font-medium text-text" aria-current="page">
              {listing.title}
            </span>
          </li>
        </ol>
      </nav>

      <header className="space-y-2" data-testid="standalone-listing-header">
        <h1 className="font-display text-2xl font-semibold text-text lg:text-3xl">
          {listing.title}
        </h1>
        <p className="text-sm text-text-2">
          {t("pdp.standalone.soldBy", { vendor: listing.vendor.name })}{" "}
          {listing.vendor.slug ? (
            <Link
              href={`/${locale}/v/${encodeURIComponent(listing.vendor.slug)}`}
              className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {t("pdp.vendor.viewStore")}
            </Link>
          ) : null}
        </p>
      </header>

      <StandaloneListingBody
        locale={locale}
        listing={toBuyBoxListing(listing)}
        sellerName={listing.vendor.name}
        images={images}
        cloudName={process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME}
        galleryLabels={{
          empty: t("pdp.gallery.empty"),
          previous: t("pdp.gallery.previous"),
          next: t("pdp.gallery.next"),
        }}
        buyBoxLabels={buyBoxLabels(t)}
      />

      <section
        aria-labelledby="standalone-listing-details-heading"
        className="rounded border border-border bg-surface p-4"
        data-testid="standalone-listing-details"
      >
        <h2 id="standalone-listing-details-heading" className="font-display text-lg text-text">
          {t("pdp.standalone.detailsHeading")}
        </h2>
        <dl className="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-text-2">{t("pdp.standalone.classLabel")}</dt>
            <dd className="font-medium text-text">
              {t("pdp.standalone.classValue", { class: listing.product_class })}
            </dd>
          </div>
          <div>
            <dt className="text-text-2">{t("pdp.standalone.conditionLabel")}</dt>
            <dd className="font-medium text-text">{t(`pdp.condition.${listing.condition}`)}</dd>
          </div>
          <div>
            <dt className="text-text-2">{t("pdp.standalone.incrementLabel")}</dt>
            <dd className="font-medium text-text">{increment}</dd>
          </div>
          <div>
            <dt className="text-text-2">{t("pdp.standalone.minimumLabel")}</dt>
            <dd className="font-medium text-text">{minimum}</dd>
          </div>
          <div>
            <dt className="text-text-2">{t("pdp.standalone.fulfilmentLabel")}</dt>
            <dd className="font-medium text-text">{fulfilment}</dd>
          </div>
          {listing.lead_time_days != null ? (
            <div>
              <dt className="text-text-2">{t("pdp.standalone.leadTimeLabel")}</dt>
              <dd className="font-medium text-text">
                {t("pdp.standalone.leadTimeDays", { days: listing.lead_time_days })}
              </dd>
            </div>
          ) : null}
          {listing.vendor_capacity_per_week != null ? (
            <div>
              <dt className="text-text-2">{t("pdp.standalone.capacityLabel")}</dt>
              <dd className="font-medium text-text">
                {t("pdp.standalone.capacityPerWeek", {
                  quantity: formatListingQuantity(
                    listing.vendor_capacity_per_week,
                    listing.sale_unit,
                    listing.unit_step_milli,
                    locale,
                    labels,
                  ),
                })}
              </dd>
            </div>
          ) : null}
          {listing.location?.landmark ? (
            <div>
              <dt className="text-text-2">{t("pdp.standalone.locationLabel")}</dt>
              <dd className="font-medium text-text">{listing.location.landmark}</dd>
            </div>
          ) : null}
        </dl>

        {listing.defect_notes?.trim() ? (
          <div className="mt-4 rounded border border-warning/40 bg-warning/10 p-3" role="note">
            <h3 className="font-medium text-text">{t("pdp.standalone.defectsHeading")}</h3>
            <p className="mt-1 whitespace-pre-line text-sm leading-6 text-text-2">
              {listing.defect_notes.trim()}
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
