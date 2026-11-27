import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { PageHeader } from "@vergeo/ui/src/page-header";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { ApiUnavailablePanel } from "../_components/api-unavailable";
import { BackToTop } from "../_components/back-to-top";
import { BrowsePager, parseBrowsePage, sliceBrowsePage } from "../_components/browse-pager";

import { ServiceFilterBoxes } from "./_components/service-filter-boxes";
import { ServiceGrid, type ServiceBrowseItem } from "./_components/service-grid";
import { SERVICE_VERTICALS } from "./_components/service-verticals";
import {
  hrefFor,
  NO_FILTERS,
  parseFilters,
  toApiQuery,
  toUrlParams,
  type ServiceFilters,
} from "./_lib/filters";

import type { Metadata } from "next";

import { CustomerRouteShell } from "@/components/customer-route-shell";

export const revalidate = 60;

type ServicesApiResponse = {
  items: ServiceBrowseItem[];
  total: number;
  verticals?: string[];
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    category?: string;
    area?: string;
    band?: string;
    rating?: string;
    avail?: string;
    page?: string;
  }>;
};

type ServicesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
  /** Unformatted message, for templates the client fills in itself. */
  raw(key: string): unknown;
};

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

async function fetchServices(
  filters: ServiceFilters,
): Promise<{ kind: "ok"; data: ServicesApiResponse } | { kind: "unavailable" }> {
  const query = toApiQuery(filters);
  const suffix = query ? `?${query}` : "";

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
  const hasFilters = Boolean(
    query.category || query.area || query.band || query.rating || query.avail,
  );

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
  const filters = parseFilters(query);
  const page = parseBrowsePage(query.page);
  const fetchResult = await fetchServices(filters);

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
  const hasActiveFilters = Object.values(toUrlParams(filters)).some(Boolean);
  const items = sliceBrowsePage(allItems, page);
  // Show every vertical the page knows; the API list may lag a deploy behind.
  const verticals = [...SERVICE_VERTICALS];
  const pagerParams = toUrlParams(filters);

  const filterLabels = {
    heading: t("browse.filters.heading"),
    more: t("browse.filters.more"),
    clear: t("browse.filters.clear"),
    remove: String(t.raw("browse.filters.remove")),
    results: t("browse.filters.results", { count: total }),
    area: t("browse.filters.area"),
    areaAll: t("browse.filters.areaAll"),
    areaPlaceholder: t("browse.areaPlaceholder"),
    filterSubmit: t("browse.filterSubmit"),
    price: t("browse.filters.price"),
    priceAny: t("browse.filters.priceAny"),
    priceBands: {
      under100: t("browse.filters.priceBands.under100"),
      mid: t("browse.filters.priceBands.mid"),
      high: t("browse.filters.priceBands.high"),
      premium: t("browse.filters.priceBands.premium"),
    },
    rating: t("browse.filters.rating"),
    ratingAny: t("browse.filters.ratingAny"),
    ratingOptions: {
      "45": t("browse.filters.ratingOptions.45"),
      "4": t("browse.filters.ratingOptions.4"),
      "3": t("browse.filters.ratingOptions.3"),
    },
    availability: t("browse.filters.availability"),
    availabilityAny: t("browse.filters.availabilityAny"),
    availabilityNow: t("browse.filters.availabilityNow"),
    all: t("categories.all"),
    categories: Object.fromEntries(
      verticals.map((vertical) => [vertical, t(`categories.${vertical}` as "categories.beauty")]),
    ),
  };

  return (
    <CustomerRouteShell width="full" className="flex flex-col gap-8 pb-8">
      <section className="flex flex-col gap-4" aria-labelledby="services-results-heading">
        <PageHeader title={t("browse.title")} subtitle={t("browse.subtitle")} />

        <div>
          <ServiceFilterBoxes
            locale={locale}
            filters={filters}
            verticals={verticals}
            areas={allItems.map((item) => item.service_area)}
            labels={filterLabels}
          />
        </div>
        <p className="m-0 text-sm text-text-3" aria-live="polite" data-testid="results-count">
          {filterLabels.results}
        </p>

        {allItems.length === 0 ? (
          <EmptyState
            title={t("browse.emptyTitle")}
            body={t("browse.emptyBody")}
            action={
              hasActiveFilters ? (
                <Link
                  href={hrefFor(locale, NO_FILTERS)}
                  className="text-sm font-semibold text-primary underline-offset-4 hover:underline"
                >
                  {filterLabels.clear}
                </Link>
              ) : undefined
            }
          />
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
                fullyBooked: t("browse.fullyBooked"),
                ratingLine: String(t.raw("browse.ratingLine")),
                archetypes: {
                  accommodation: t("templates.archetypes.accommodation"),
                  appointment: t("templates.archetypes.appointment"),
                  membership: t("templates.archetypes.membership"),
                  on_site: t("templates.archetypes.on_site"),
                  rental: t("templates.archetypes.rental"),
                  ticketed: t("templates.archetypes.ticketed"),
                  professional: t("templates.archetypes.professional"),
                },
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
