import { DEFAULT_LOCALE, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import {
  buildAbsoluteUrl,
  buildCanonicalAlternates,
  buildLocaleCanonical,
  buildOrganizationJsonLd,
  buildSearchActionUrlTemplate,
  buildWebSiteJsonLd,
  JsonLdScript,
} from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BannerRow } from "./_components/banner-row";
import { CategoryGrid } from "./_components/category-grid";
import { EventsRow } from "./_components/events-row";
import { FeaturedCollections } from "./_components/featured-collections";
import { FlashDeal } from "./_components/flash-deal";
import { HomeHero } from "./_components/hero";
import {
  HomeHeroBand,
  HomeProductRail,
  HomeSellCta,
  HomeServicesRail,
  HomeVendorsRail,
  loadHomeDefaultData,
  pickHeroVisualPublicId,
} from "./_components/home-default";
import { planHomeLayout } from "./_components/home-layout";
import { HomeRecentlyViewedRail } from "./_components/home-recently-viewed-rail";
import { HomeTrustStrip } from "./_components/home-trust-strip";
import { loadHomeMerchData, pickSlot, type HomeSectionKey } from "./_components/merch-data";
import { MerchPreviewBanner } from "./_components/merch-preview-banner";

import type { Metadata } from "next";

export const revalidate = 60;

type CatalogTranslator = (key: string, values?: Record<string, string | number>) => string;

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ merch_preview?: string | string[] }>;
};

function readMerchPreviewParam(
  searchParams: { merch_preview?: string | string[] } | undefined,
): string | null {
  const raw = searchParams?.merch_preview;
  if (typeof raw === "string" && raw.trim().length > 0) {
    return raw.trim();
  }
  if (Array.isArray(raw)) {
    const first = raw.find((value) => typeof value === "string" && value.trim().length > 0);
    return first?.trim() ?? null;
  }
  return null;
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

async function getCatalogTranslator(locale: string) {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

  return createTranslator({ locale, messages, namespace: "catalog" });
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const resolvedSearchParams = await searchParams;
  const merchPreview = readMerchPreviewParam(resolvedSearchParams);
  const t = await getCatalogTranslator(locale);

  return {
    title: t("home.meta.title"),
    description: t("home.meta.description"),
    alternates: buildCanonicalAlternates(locale),
    openGraph: {
      title: t("home.meta.title"),
      description: t("home.meta.description"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale),
    },
    robots: merchPreview
      ? { index: false, follow: false }
      : {
          index: true,
          follow: true,
        },
  };
}

function renderCampaignSection(
  sectionKey: HomeSectionKey,
  locale: string,
  t: CatalogTranslator,
  slots: Awaited<ReturnType<typeof loadHomeMerchData>>["slots"],
  categories: Awaited<ReturnType<typeof loadHomeMerchData>>["categories"],
) {
  switch (sectionKey) {
    case "hero":
      return <HomeHero key={sectionKey} slot={pickSlot(slots, "hero")} locale={locale} t={t} />;
    case "banner_row":
      return (
        <BannerRow key={sectionKey} slot={pickSlot(slots, "banner_row")} locale={locale} t={t} />
      );
    case "flash_deal":
      return (
        <FlashDeal key={sectionKey} slot={pickSlot(slots, "flash_deal")} locale={locale} t={t} />
      );
    case "events_row":
      return (
        <EventsRow key={sectionKey} slot={pickSlot(slots, "events_row")} locale={locale} t={t} />
      );
    case "featured_collections":
      return (
        <FeaturedCollections
          key={sectionKey}
          slot={pickSlot(slots, "featured_collections")}
          locale={locale}
          t={t}
        />
      );
    case "category_grid":
      return (
        <CategoryGrid
          key={sectionKey}
          slot={pickSlot(slots, "category_grid")}
          categories={categories}
          locale={locale}
          t={t}
        />
      );
    default:
      return null;
  }
}

export default async function ShopHomePage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const resolvedSearchParams = await searchParams;
  const merchPreview = readMerchPreviewParam(resolvedSearchParams);
  setRequestLocale(locale);

  const [tRaw, merch, baseMessages] = await Promise.all([
    getCatalogTranslator(locale),
    loadHomeMerchData({ merchPreview }),
    getMessages(),
  ]);
  const t = tRaw as unknown as CatalogTranslator;
  const tCommon = createTranslator({
    locale,
    messages: baseMessages as AbstractIntlMessages,
    namespace: "common",
  });

  // Always load catalogue rails so partial/placeholder merch cannot suppress discovery.
  const defaultData = await loadHomeDefaultData(merch.categories);
  const plan = planHomeLayout(merch.slots, merch.categories, defaultData);

  const trustLabels = {
    ariaLabel: t("home.trust.ariaLabel"),
    sellers: t("home.trust.sellers"),
    fulfillment: t("home.trust.fulfillment"),
    returns: t("home.trust.returns"),
    escrow: t("home.trust.escrow"),
    escrowStep1: t("home.hero.escrowStep1"),
    escrowStep2: t("home.hero.escrowStep2"),
    escrowStep3: t("home.hero.escrowStep3"),
  };

  const railLabels = {
    vendor: t("plp.card.vendor"),
    noReviews: t("plp.card.noReviews"),
    reviewCount: t("plp.card.reviewCount"),
    quickAdd: t("plp.card.quickAdd"),
    quickAddError: t("plp.card.quickAddError"),
    wishlist: t("plp.card.wishlist"),
    wishlistRemove: t("plp.card.wishlistRemove"),
    outOfStock: t("plp.card.outOfStock"),
    discount: t("plp.card.discount"),
    sampleListing: t("home.demo.sampleListing"),
    mediaEmpty: t("plp.card.mediaEmpty"),
    conditionNew: t("plp.card.conditionNew"),
    conditionRefurbished: t("plp.card.conditionRefurbished"),
    logistics: {
      nearest: t("plp.card.pill.nearest"),
      belowMedian: t("plp.card.pill.belowMedian"),
      delivery: t("plp.card.pill.delivery"),
      pickup: t("plp.card.pill.pickup"),
    },
  };

  // Audit hierarchy: categories before flash/campaign; events after product rails.
  const earlyCampaignKeys = plan.campaignSectionKeys.filter(
    (key) => key !== "hero" && key !== "category_grid" && key !== "events_row",
  );
  const showEventsRow = plan.campaignSectionKeys.includes("events_row");

  const organizationJsonLd = buildOrganizationJsonLd({ name: "Vergeo5" });
  const websiteJsonLd = buildWebSiteJsonLd({
    name: "Vergeo5",
    url: buildAbsoluteUrl(buildLocaleCanonical(DEFAULT_LOCALE)),
    searchUrlTemplate: buildSearchActionUrlTemplate(DEFAULT_LOCALE),
  });

  const brandName = tCommon("app.name");

  return (
    <div className="flex flex-col gap-6 lg:gap-10">
      <JsonLdScript data={[organizationJsonLd, websiteJsonLd]} />
      {merch.isPreviewMode ? <MerchPreviewBanner message={t("home.merchPreview.banner")} /> : null}
      {plan.useCampaignHero ? (
        renderCampaignSection("hero", locale, t, merch.slots, merch.categories)
      ) : (
        // Merch-first default hero even when rails are empty — brand must still
        // lead the first viewport (audit §4.1). Campaign heroes stay opt-in.
        <HomeHeroBand
          locale={locale}
          t={t}
          brandName={brandName}
          visualPublicId={pickHeroVisualPublicId(defaultData.newest)}
        />
      )}

      <HomeTrustStrip labels={trustLabels} />

      {plan.showCategoryGrid ? (
        <CategoryGrid
          slot={pickSlot(merch.slots, "category_grid")}
          categories={merch.categories}
          locale={locale}
          t={t}
        />
      ) : null}

      {earlyCampaignKeys.map((sectionKey) =>
        renderCampaignSection(sectionKey, locale, t, merch.slots, merch.categories),
      )}

      <HomeRecentlyViewedRail
        locale={locale}
        labels={{
          title: t("home.rails.recentTitle"),
          viewAll: t("home.rails.viewAll"),
          viewProduct: t("home.rails.recentViewProduct"),
          view: t("home.rails.recentView"),
        }}
      />

      {plan.showDefaultRails ? (
        <>
          <HomeProductRail
            id="home-rail-new"
            title={t("home.rails.newTitle")}
            viewAllHref={`/${locale}/c/all`}
            viewAllLabel={t("home.rails.viewAll")}
            listings={defaultData.newest}
            locale={locale}
            labels={railLabels}
            priorityCount={2}
          />
          {defaultData.departmentRails.map((rail) => (
            <HomeProductRail
              key={rail.category.id}
              id={`home-rail-${rail.category.slug}`}
              title={t("home.rails.departmentTitle", { category: rail.category.name })}
              viewAllHref={`/${locale}/c/${rail.category.slug}`}
              viewAllLabel={t("home.rails.viewAll")}
              listings={rail.listings}
              locale={locale}
              labels={railLabels}
            />
          ))}
        </>
      ) : null}

      {showEventsRow
        ? renderCampaignSection("events_row", locale, t, merch.slots, merch.categories)
        : null}

      {plan.showDefaultRails ? (
        <>
          <HomeServicesRail
            id="home-rail-services"
            title={t("home.rails.servicesTitle")}
            viewAllHref={`/${locale}/services`}
            viewAllLabel={t("home.rails.viewAll")}
            services={defaultData.services}
            locale={locale}
            labels={{
              provider: t("home.rails.services.provider"),
              fromPrice: t("home.rails.services.fromPrice"),
              noReviews: t("home.rails.services.noReviews"),
              view: t("home.rails.services.view"),
            }}
          />
          <HomeVendorsRail
            id="home-rail-vendors"
            title={t("home.rails.vendorsTitle")}
            viewAllHref={`/${locale}/directory`}
            viewAllLabel={t("home.rails.viewAll")}
            vendors={defaultData.topVendors}
            locale={locale}
            labels={{
              listings: t("home.rails.vendors.listings"),
              reviews: t("home.rails.vendors.reviews"),
              rating: t("home.rails.vendors.rating"),
              noReviews: t("home.rails.vendors.noReviews"),
              preferred: t("home.rails.vendors.preferred"),
              verified: t("home.rails.vendors.verified"),
              location: t("home.rails.vendors.location"),
              view: t("home.rails.vendors.view"),
            }}
          />
        </>
      ) : null}

      {plan.showSellCta ? <HomeSellCta locale={locale} t={t} /> : null}
    </div>
  );
}
