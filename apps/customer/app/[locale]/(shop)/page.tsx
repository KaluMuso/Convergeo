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
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { BackToTop } from "./_components/back-to-top";
import { BannerRow } from "./_components/banner-row";
import { CategoryGrid } from "./_components/category-grid";
import { buildVendorLadderLabels } from "./_components/directory/vendor-ladder-labels";
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
  type HomeDefaultData,
} from "./_components/home-default";
import { HomeEmptyRails } from "./_components/home-empty-rails";
import { isRenderableSection } from "./_components/home-feed/feed-types";
import {
  buildFeedLabels,
  HomeFeed,
  loadHomeFeedFirstPage,
} from "./_components/home-feed/home-feed";
import {
  HomeListingStream,
  listingIdsOf,
  loadHomeStreamFirstPage,
} from "./_components/home-feed/home-stream";
import { planHomeLayout } from "./_components/home-layout";
import { HomeRailFallback } from "./_components/home-rail-fallback";
import { HomeRecentlyViewedRail } from "./_components/home-recently-viewed-rail";
import { HomeTrustStrip } from "./_components/home-trust-strip";
import { loadHomeMerchData, pickSlot, type HomeSectionKey } from "./_components/merch-data";
import { MerchPreviewBanner } from "./_components/merch-preview-banner";
import { buildOfferBadgeLabels } from "./_components/offers/offer-badge";
import { catalogDeliveryLabels, catalogMadeToOrderLabels } from "./_components/plp/delivery-labels";

import type { Metadata } from "next";

export const revalidate = 60;

const EMPTY_DEFAULT_DATA: HomeDefaultData = {
  deals: [],
  newest: [],
  departmentRails: [],
  services: [],
  topVendors: [],
};

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
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
  } as AbstractIntlMessages;

  return createTranslator({ locale, messages, namespace: "catalog" });
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }
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
  // Belt-and-suspenders alongside the root layout's own guard: React can start
  // rendering this segment concurrently with the layout, so relying solely on
  // the layout's `notFound()` still lets an invalid locale (e.g. a bot request
  // to a locale-less path the middleware matcher didn't catch) reach the
  // `IntlMessageFormat` calls below, which throw for anything that isn't a
  // valid BCP-47 tag — see apps/customer/middleware.ts.
  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }
  const resolvedSearchParams = await searchParams;
  const merchPreview = readMerchPreviewParam(resolvedSearchParams);
  setRequestLocale(locale);

  // Started before any await so it overlaps with merch/feed; consumed (awaited)
  // only inside the streamed Suspense sections below.
  const streamPromise = loadHomeStreamFirstPage();
  const [tRaw, merch, baseMessages, directoryMessages, feedPage] = await Promise.all([
    getCatalogTranslator(locale),
    loadHomeMerchData({ merchPreview }),
    getMessages(),
    loadNamespace(locale as Locale, "directory"),
    loadHomeFeedFirstPage(locale),
  ]);
  const t = tRaw as unknown as CatalogTranslator;
  // Card/rail labels cross into client components as serializable strings and are
  // interpolated there, so messages holding `{…}` placeholders are read raw —
  // `t()` cannot format them without values and falls back to the bare key path.
  const raw = (key: string) => String(tRaw.raw(key));
  const tDirectory = createTranslator({
    locale,
    messages: { directory: directoryMessages } as AbstractIntlMessages,
    namespace: "directory",
  }) as unknown as (key: string) => string;
  const vendorLadderLabels = buildVendorLadderLabels(tDirectory);
  const tCommon = createTranslator({
    locale,
    messages: baseMessages as AbstractIntlMessages,
    namespace: "common",
  });

  // Always load catalogue rails so partial/placeholder merch cannot suppress discovery.
  // Second wave (needs the category paths). Not awaited: the hero, trust strip and
  // category grid paint from merch + feed alone, and the rails stream in after.
  const defaultPromise = loadHomeDefaultData(merch.categories);
  // With categories present `hasDefault` is true whatever the rails hold, so the
  // shell plan is exact without the rails. With none, fall back to awaiting them so
  // the layout mode is decided on the real data (rare: categories API degraded).
  const eagerDefault = merch.categories.length === 0 ? await defaultPromise : null;
  const plan = planHomeLayout(merch.slots, merch.categories, eagerDefault ?? EMPTY_DEFAULT_DATA);

  const trustLabels = {
    ariaLabel: t("home.trustStrip.ariaLabel"),
    cod: t("home.trustStrip.cod"),
    verified: t("home.trustStrip.verified"),
    lusaka: t("home.trustStrip.lusaka"),
    returns: t("home.trustStrip.returns"),
  };

  const railLabels = {
    vendor: raw("plp.card.vendor"),
    noReviews: t("plp.card.noReviews"),
    reviewCount: raw("plp.card.reviewCount"),
    quickAdd: t("plp.card.quickAdd"),
    quickAddError: t("plp.card.quickAddError"),
    wishlist: t("plp.card.wishlist"),
    wishlistRemove: t("plp.card.wishlistRemove"),
    outOfStock: t("plp.card.outOfStock"),
    discount: raw("plp.card.discount"),
    sampleListing: t("home.demo.sampleListing"),
    mediaEmpty: t("plp.card.mediaEmpty"),
    conditionNew: t("plp.card.conditionNew"),
    conditionRefurbished: t("plp.card.conditionRefurbished"),
    conditionUsed: t("plp.card.conditionUsed"),
    delivery: catalogDeliveryLabels((key) => String(tRaw.raw(key))),
    madeToOrder: catalogMadeToOrderLabels((key) => String(tRaw.raw(key))),
    logistics: {
      nearest: raw("plp.card.pill.nearest"),
      belowMedian: t("plp.card.pill.belowMedian"),
      delivery: t("plp.card.pill.delivery"),
      pickup: t("plp.card.pill.pickup"),
    },
    offerBadge: buildOfferBadgeLabels(raw),
  };

  // Admin-governed feed (home_feed_sections) supersedes the hard-coded default
  // rails whenever it resolves to at least one section; otherwise the legacy
  // rails below remain the fallback (API down / feed not configured).
  const useAdminFeed = feedPage.sections.some(isRenderableSection);
  const feedLabels = buildFeedLabels(
    tRaw as unknown as Parameters<typeof buildFeedLabels>[0],
    railLabels,
  );

  const streamLabels = {
    title: t("home.feed.stream.title"),
    loadMore: t("home.feed.stream.loadMore"),
    loading: t("home.feed.loadingMore"),
    moreLoaded: raw("home.feed.stream.moreLoaded"),
    endOfResults: t("home.feed.end"),
    loadError: t("home.feed.loadError"),
    retry: t("home.feed.retry"),
    empty: {
      title: t("home.feed.stream.emptyTitle"),
      body: t("home.feed.stream.emptyBody"),
      cta: t("home.feed.stream.emptyCta"),
    },
  };

  // Audit hierarchy: categories before flash/campaign; events after product rails.
  const earlyCampaignKeys = plan.campaignSectionKeys.filter(
    (key) => key !== "hero" && key !== "category_grid" && key !== "events_row",
  );
  const showEventsRow = plan.campaignSectionKeys.includes("events_row");

  const organizationJsonLd = buildOrganizationJsonLd({ name: "Convergeo" });
  const websiteJsonLd = buildWebSiteJsonLd({
    name: "Convergeo",
    url: buildAbsoluteUrl(buildLocaleCanonical(DEFAULT_LOCALE)),
    searchUrlTemplate: buildSearchActionUrlTemplate(DEFAULT_LOCALE),
  });

  const brandName = tCommon("app.name");

  async function HomeDealsSection() {
    const defaultData = eagerDefault ?? (await defaultPromise);
    // Existing GET /deals only; hides itself when there are no live deals.
    return (
      <HomeProductRail
        id="home-rail-deals"
        title={t("home.dealsRail.title")}
        viewAllHref={`/${locale}/deals`}
        viewAllLabel={t("home.rails.viewAll")}
        listings={defaultData.deals}
        locale={locale}
        labels={railLabels}
        priorityCount={2}
      />
    );
  }

  async function HomeLowerSections() {
    const [defaultData, streamLoad] = await Promise.all([
      eagerDefault ?? defaultPromise,
      streamPromise,
    ]);
    const fullPlan = planHomeLayout(merch.slots, merch.categories, defaultData);
    const homeIsEmpty =
      !useAdminFeed &&
      !fullPlan.showDefaultRails &&
      defaultData.deals.length === 0 &&
      !(streamLoad.status === "ok" && streamLoad.page.items.length > 0);

    return (
      <>
        {fullPlan.showDefaultRails && !useAdminFeed ? (
          <>
            <HomeProductRail
              id="home-rail-new"
              title={t("home.rails.newTitle")}
              viewAllHref={`/${locale}/c/all`}
              viewAllLabel={t("home.rails.viewAll")}
              listings={defaultData.newest}
              locale={locale}
              labels={railLabels}
              priorityCount={0}
            />
            {defaultData.departmentRails.map((rail) => (
              <HomeProductRail
                key={rail.category.id}
                id={`home-rail-${rail.category.slug}`}
                title={t("home.rails.departmentTitle", {
                  category: rail.category.name,
                })}
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

        {fullPlan.showDefaultRails && !useAdminFeed ? (
          <>
            <HomeServicesRail
              id="home-rail-services"
              title={t("home.rails.servicesTitle")}
              viewAllHref={`/${locale}/services`}
              viewAllLabel={t("home.rails.viewAll")}
              services={defaultData.services}
              locale={locale}
              labels={{
                provider: raw("home.rails.services.provider"),
                fromPrice: t("home.rails.services.fromPrice"),
                noReviews: t("home.rails.services.noReviews"),
                view: t("home.rails.services.view"),
              }}
            />
            <HomeVendorsRail
              id="home-rail-vendors"
              title={t("home.rails.vendorsTitle")}
              viewAllHref={`/${locale}/vendors`}
              viewAllLabel={t("home.rails.viewAll")}
              vendors={defaultData.topVendors}
              locale={locale}
              labels={{
                listings: t("home.rails.vendors.listings"),
                reviews: t("home.rails.vendors.reviews"),
                rating: raw("home.rails.vendors.rating"),
                noReviews: t("home.rails.vendors.noReviews"),
                preferred: t("home.rails.vendors.preferred"),
                verified: t("home.rails.vendors.verified"),
                location: t("home.rails.vendors.location"),
                view: t("home.rails.vendors.view"),
                trustLabels: vendorLadderLabels,
              }}
            />
          </>
        ) : null}

        {fullPlan.showSellCta ? <HomeSellCta locale={locale} t={t} /> : null}

        {/* Infinite feed is last so loading more never pushes static modules away. */}
        {useAdminFeed ? (
          <HomeFeed
            page={feedPage}
            locale={locale}
            labels={feedLabels}
            streamFollows={streamLoad.status === "ok" && streamLoad.page.items.length > 0}
          />
        ) : null}

        {homeIsEmpty ? (
          <HomeEmptyRails
            locale={locale}
            labels={{
              title: t("home.feed.stream.emptyTitle"),
              body: t("home.feed.stream.emptyBody"),
              browse: t("home.hero.primaryCta"),
              sell: t("home.feed.stream.emptyCta"),
            }}
          />
        ) : (
          /* "Popular now": first batch is SSR; only later pages load on the client. */
          <HomeListingStream
            stream={streamLoad}
            sectionListingIds={listingIdsOf(feedPage.sections)}
            locale={locale}
            cardLabels={railLabels}
            labels={streamLabels}
          />
        )}
      </>
    );
  }

  return (
    <div className="v-home-fab-pad flex flex-col gap-4 lg:gap-6">
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
          sponsoredSlides={feedPage.carousel}
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

      <Suspense fallback={<HomeRailFallback testId="home-deals-fallback" />}>
        <HomeDealsSection />
      </Suspense>

      {earlyCampaignKeys.map((sectionKey) =>
        renderCampaignSection(sectionKey, locale, t, merch.slots, merch.categories),
      )}

      <HomeRecentlyViewedRail
        locale={locale}
        labels={{
          title: t("home.rails.recentTitle"),
          viewAll: t("home.rails.viewAll"),
          viewProduct: raw("home.rails.recentViewProduct"),
          view: t("home.rails.recentView"),
        }}
      />

      <Suspense fallback={<HomeRailFallback testId="home-rails-fallback" rows={2} />}>
        <HomeLowerSections />
      </Suspense>
      <BackToTop label={t("plp.backToTop")} />
    </div>
  );
}
