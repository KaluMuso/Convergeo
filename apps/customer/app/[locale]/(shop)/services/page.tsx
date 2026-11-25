import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { PageHeader } from "@vergeo/ui/src/page-header";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { ApiUnavailablePanel } from "../_components/api-unavailable";
import { BackToTop } from "../_components/back-to-top";
import { BrowsePager, parseBrowsePage, sliceBrowsePage } from "../_components/browse-pager";

import { ServiceGrid, type ServiceBrowseItem } from "./_components/service-grid";
import { SERVICE_VERTICALS } from "./_components/service-verticals";
import { VerticalFilterChips } from "./_components/vertical-filter-chips";

import type { Metadata } from "next";

import { CustomerRouteShell } from "@/components/customer-route-shell";

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
    page?: string;
  }>;
};

type ServicesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
  /** Unformatted message, for templates the client fills in itself. */
  raw(key: string): unknown;
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
  const messages = {
    ...baseMessages,
    services: servicesMessages,
  } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "services",
  }) as unknown as ServicesTranslator;
}

async function fetchServices(params: {
  category: string | null;
  area: string;
}): Promise<{ kind: "ok"; data: ServicesApiResponse } | { kind: "unavailable" }> {
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
      return { kind: "unavailable" };
    }
    const response = await fetch(url, {
      next: { revalidate, tags: ["services"] },
    });
    if (!response.ok) {
      return { kind: "unavailable" };
    }
    return { kind: "ok", data: (await response.json()) as ServicesApiResponse };
  } catch {
    return { kind: "unavailable" };
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
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const tCatalog = createTranslator({
    locale,
    messages: { catalog: catalogMessages },
    namespace: "catalog",
  }) as ServicesTranslator;
  const category = parseCategory(query.category);
  const area = query.area ?? "";
  const page = parseBrowsePage(query.page);
  const fetchResult = await fetchServices({ category, area });

  if (fetchResult.kind === "unavailable") {
    return (
      <CustomerRouteShell width="full" className="flex flex-col gap-8 pb-8">
        <ApiUnavailablePanel
          retryHref={`/${locale}/services`}
          labels={{
            title: t("browse.unavailableTitle"),
            body: t("browse.unavailableBody"),
            retry: t("browse.unavailableRetry"),
          }}
          testId="services-unavailable"
        />
      </CustomerRouteShell>
    );
  }

  const data = fetchResult.data;
  const allItems = data.items;
  const total = data.total ?? allItems.length;
  const items = sliceBrowsePage(allItems, page);
  const verticals = data.verticals ?? [...SERVICE_VERTICALS];
  const pagerParams = { category: category ?? undefined, area: area || undefined };

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
    <CustomerRouteShell width="full" className="flex flex-col gap-8 pb-8">
      <section className="flex flex-col gap-4" aria-labelledby="services-results-heading">
        <PageHeader title={t("browse.title")} subtitle={t("browse.subtitle")} />

        <div>
          <Suspense fallback={null}>
            <VerticalFilterChips
              locale={locale}
              labels={filterLabels}
              activeCategory={category}
              activeArea={area}
              verticals={verticals}
            />
          </Suspense>
        </div>

        {allItems.length === 0 ? (
          <EmptyState title={t("browse.emptyTitle")} body={t("browse.emptyBody")} />
        ) : (
          <>
            <ServiceGrid
              items={items}
              locale={locale}
              labels={{
                viewService: t("browse.viewService"),
                fromPrice: String(t.raw("browse.fromPrice")),
                askForQuote: t("browse.askForQuote"),
                badges: {
                  fast: t("badges.fast"),
                  same_day: t("badges.same_day"),
                  slow: t("badges.slow"),
                },
                preferredBadge: t("browse.preferredBadge"),
                free: t("detail.free"),
              }}
            />
            <BrowsePager
              locale={locale}
              pathname="/services"
              searchParams={pagerParams}
              page={page}
              total={total}
              labels={{
                previous: t("browse.pagination.previous"),
                next: t("browse.pagination.next"),
                page: t("browse.pagination.page"),
              }}
            />
            <BackToTop label={tCatalog("plp.backToTop")} />
          </>
        )}
      </section>

      <section
        className="flex flex-col gap-5 rounded-lg bg-panel px-6 py-8 text-panel-text shadow-2 md:flex-row md:items-center md:justify-between md:px-10"
        aria-labelledby="services-provider-cta"
      >
        <div className="max-w-2xl space-y-2">
          <h2 id="services-provider-cta" className="font-display text-h2 text-panel-text">
            {t("browse.providerCta")}
          </h2>
          <p className="text-sm leading-relaxed text-panel-muted">{t("browse.providerPitch")}</p>
        </div>
        <Link
          href={`/${locale}/sell`}
          className="inline-flex min-h-11 shrink-0 items-center justify-center rounded bg-primary px-6 text-sm font-semibold text-[var(--primary-btn-fg)] transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("browse.providerCta")}
        </Link>
      </section>
    </CustomerRouteShell>
  );
}
