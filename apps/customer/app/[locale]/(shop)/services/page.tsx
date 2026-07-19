import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { absoluteApiUrl } from "../../../../lib/api-base-url";

import { ServiceGrid, type ServiceBrowseItem } from "./_components/service-grid";
import { SERVICE_VERTICALS, VerticalFilterChips } from "./_components/vertical-filter-chips";

import type { Metadata } from "next";

export const revalidate = 60;

type ServicesApiResponse = {
  items: ServiceBrowseItem[];
  total: number;
  verticals: string[];
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    category?: string;
    area?: string;
  }>;
};

type ServicesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

function parseCategory(value: string | undefined): string | null {
  if (!value) {
    return null;
  }
  if ((SERVICE_VERTICALS as readonly string[]).includes(value)) {
    return value;
  }
  return null;
}

async function getServicesTranslator(locale: string): Promise<ServicesTranslator> {
  const baseMessages = await getMessages();
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const messages = { ...baseMessages, services: servicesMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "services",
  }) as unknown as ServicesTranslator;
}

async function fetchServices(params: {
  category: string | null;
  area: string;
}): Promise<ServicesApiResponse | null> {
  const search = new URLSearchParams();
  if (params.category) {
    search.set("category", params.category);
  }
  if (params.area.trim()) {
    search.set("area", params.area.trim());
  }
  const suffix = search.toString() ? `?${search.toString()}` : "";

  try {
    const url = absoluteApiUrl(`/services${suffix}`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: { revalidate, tags: ["services"] },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ServicesApiResponse;
  } catch {
    return null;
  }
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const query = await searchParams;
  const t = await getServicesTranslator(locale);
  const hasFilters = Boolean(query.category || query.area);

  return {
    title: t("browse.title"),
    description: t("browse.subtitle"),
    alternates: buildCanonicalAlternates(locale, "services"),
    openGraph: {
      title: t("browse.title"),
      description: t("browse.subtitle"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "services"),
    },
    robots: { index: !hasFilters, follow: true },
  };
}

export default async function ServicesPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);

  const t = await getServicesTranslator(locale);
  const category = parseCategory(query.category);
  const area = query.area ?? "";
  const data = await fetchServices({ category, area });
  const items = data?.items ?? [];
  const verticals = data?.verticals ?? [...SERVICE_VERTICALS];

  const filterLabels = {
    verticalLabel: t("browse.verticalLabel"),
    areaLabel: t("browse.areaLabel"),
    areaPlaceholder: t("browse.areaPlaceholder"),
    filterSubmit: t("browse.filterSubmit"),
    preferredBadge: t("browse.preferredBadge"),
    categories: {
      all: t("categories.all"),
      beauty: t("categories.beauty"),
      "food-catering": t("categories.food-catering"),
      auto: t("categories.auto"),
      "printing-creative": t("categories.printing-creative"),
      "home-services": t("categories.home-services"),
      "tech-services": t("categories.tech-services"),
      cleaning: t("categories.cleaning"),
      tailoring: t("categories.tailoring"),
    },
  };

  return (
    <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <section className="overflow-hidden rounded-lg bg-panel px-5 py-8 text-panel-text sm:px-8 sm:py-10">
        <div className="max-w-2xl space-y-3">
          <h1 className="font-display text-h1 text-panel-text">{t("browse.title")}</h1>
          <p className="text-body text-panel-muted">{t("browse.subtitle")}</p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href={`/${locale}/sell`}
              className="inline-flex min-h-11 items-center rounded bg-panel-text px-5 text-sm font-semibold text-panel transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {t("browse.providerCta")}
            </Link>
            <span className="text-sm text-panel-muted">{t("browse.providerPitch")}</span>
          </div>
        </div>
      </section>

      <Suspense fallback={null}>
        <VerticalFilterChips
          locale={locale}
          labels={filterLabels}
          activeCategory={category}
          activeArea={area}
          verticals={verticals}
        />
      </Suspense>

      {items.length === 0 ? (
        <EmptyState title={t("browse.emptyTitle")} body={t("browse.emptyBody")} />
      ) : (
        <ServiceGrid
          items={items}
          locale={locale}
          labels={{
            viewService: t("browse.viewService"),
            fromPrice: t("browse.fromPrice"),
            askForQuote: t("browse.askForQuote"),
            badges: {
              fast: t("badges.fast"),
              same_day: t("badges.same_day"),
              slow: t("badges.slow"),
            },
            preferredBadge: t("browse.preferredBadge"),
          }}
        />
      )}
    </div>
  );
}
