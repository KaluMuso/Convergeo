import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BannerRow } from "./_components/banner-row";
import { CategoryGrid } from "./_components/category-grid";
import { EventsRow } from "./_components/events-row";
import { FeaturedCollections } from "./_components/featured-collections";
import { HomeHero } from "./_components/hero";
import {
  getRenderableSectionKeys,
  loadHomeMerchData,
  pickSlot,
  type HomeSectionKey,
} from "./_components/merch-data";

import type { Metadata } from "next";

export const revalidate = 60;

type CatalogTranslator = (key: string, values?: Record<string, string | number>) => string;

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

async function getCatalogTranslator(locale: string) {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

  return createTranslator({ locale, messages, namespace: "catalog" });
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
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
    robots: {
      index: true,
      follow: true,
    },
  };
}

function renderSection(
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

export default async function ShopHomePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const [tRaw, data] = await Promise.all([getCatalogTranslator(locale), loadHomeMerchData()]);
  const t = tRaw as unknown as CatalogTranslator;
  const sectionKeys = getRenderableSectionKeys(data.slots, data.categories);

  return (
    <div className="flex flex-col gap-6">
      {sectionKeys.length > 0 ? (
        sectionKeys.map((sectionKey) =>
          renderSection(sectionKey, locale, t, data.slots, data.categories),
        )
      ) : (
        <HomeHero locale={locale} t={t} />
      )}
    </div>
  );
}
