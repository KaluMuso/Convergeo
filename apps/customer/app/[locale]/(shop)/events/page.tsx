import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { absoluteApiUrl } from "../../../../lib/api-base-url";
import { BackToTop } from "../_components/back-to-top";
import {
  DateFilterChips,
  EVENT_CATEGORIES,
  type EventCategory,
  type EventDateWindow,
} from "../_components/events/date-filter-chips";
import { EventGrid, type EventBrowseItem } from "../_components/events/event-grid";

import type { Metadata } from "next";

export const revalidate = 60;

type EventsApiResponse = {
  items: EventBrowseItem[];
  total: number;
  categories: string[];
  calendar_dates: string[];
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    date_window?: string;
    category?: string;
  }>;
};

type EventsTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

function parseDateWindow(value: string | undefined): EventDateWindow {
  if (value === "this_weekend" || value === "all") {
    return value;
  }
  return "tonight";
}

function parseCategory(value: string | undefined): EventCategory | null {
  if (!value) {
    return null;
  }
  if ((EVENT_CATEGORIES as readonly string[]).includes(value)) {
    return value as EventCategory;
  }
  return null;
}

function formatFeaturedEventDate(iso: string | null, locale: string): string | null {
  if (!iso) {
    return null;
  }
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Africa/Lusaka",
  }).format(new Date(iso));
}

async function getEventsTranslator(locale: string): Promise<EventsTranslator> {
  const baseMessages = await getMessages();
  const eventsMessages = await loadNamespace(locale as Locale, "events");
  const messages = { ...baseMessages, events: eventsMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "events",
  }) as unknown as EventsTranslator;
}

async function fetchEvents(params: {
  dateWindow: EventDateWindow;
  category: EventCategory | null;
}): Promise<EventsApiResponse | null> {
  const search = new URLSearchParams();
  if (params.dateWindow !== "all") {
    search.set("date_window", params.dateWindow);
  }
  if (params.category) {
    search.set("category", params.category);
  }

  const suffix = search.toString() ? `?${search.toString()}` : "";

  try {
    const url = absoluteApiUrl(`/events${suffix}`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: { revalidate, tags: ["events"] },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as EventsApiResponse;
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
  const t = await getEventsTranslator(locale);
  const hasFilters =
    (query.date_window !== undefined && query.date_window !== "tonight") || Boolean(query.category);

  return {
    title: t("browse.title"),
    description: t("browse.subtitle"),
    alternates: buildCanonicalAlternates(locale, "events"),
    openGraph: {
      title: t("browse.title"),
      description: t("browse.subtitle"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "events"),
    },
    robots: { index: !hasFilters, follow: true },
  };
}

export default async function EventsPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);

  const t = await getEventsTranslator(locale);
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const tCatalog = createTranslator({
    locale,
    messages: { catalog: catalogMessages },
    namespace: "catalog",
  }) as EventsTranslator;
  const dateWindow = parseDateWindow(query.date_window);
  const category = parseCategory(query.category);
  const data = await fetchEvents({ dateWindow, category });
  const items = data?.items ?? [];
  const calendarDates = data?.calendar_dates ?? [];
  const featuredEvent = items[0];
  const remainingEvents = items.slice(1);

  const filterLabels = {
    tonight: t("filters.tonight"),
    thisWeekend: t("filters.thisWeekend"),
    allDates: t("filters.allDates"),
    categoryLabel: t("filters.categoryLabel"),
    calendarLabel: t("browse.calendarLabel"),
    categories: {
      all: t("categories.all"),
      workshops: t("categories.workshops"),
      "comedy-theatre": t("categories.comedy-theatre"),
      "pop-up-dinners": t("categories.pop-up-dinners"),
      "cultural-arts": t("categories.cultural-arts"),
      "lifestyle-community": t("categories.lifestyle-community"),
      "free-rsvp": t("categories.free-rsvp"),
    },
  };

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-10 pb-8">
      <header className="overflow-hidden rounded-lg bg-panel text-panel-text shadow-2">
        <div className="grid min-h-[24rem] lg:grid-cols-[minmax(0,0.95fr)_minmax(24rem,1.05fr)]">
          <div className="flex flex-col justify-center gap-5 p-6 md:p-10 lg:p-12">
            <div className="space-y-2">
              <h1 className="font-display text-h2 text-panel-text">{t("browse.title")}</h1>
              {featuredEvent ? (
                <>
                  <h2 className="font-display text-hero text-panel-text">{featuredEvent.title}</h2>
                  <div className="space-y-1 text-sm text-panel-muted">
                    {formatFeaturedEventDate(featuredEvent.next_starts_at, locale) ? (
                      <p>{formatFeaturedEventDate(featuredEvent.next_starts_at, locale)}</p>
                    ) : null}
                    <p>{featuredEvent.venue ?? featuredEvent.organiser.display_name}</p>
                  </div>
                </>
              ) : (
                <p className="max-w-xl text-body leading-relaxed text-panel-muted">
                  {t("browse.subtitle")}
                </p>
              )}
            </div>

            {featuredEvent ? (
              <div className="flex flex-wrap items-center gap-4">
                {featuredEvent.is_sold_out ? (
                  <Badge variant="sold_out" label={t("browse.soldOut")} />
                ) : featuredEvent.is_free ? (
                  <Badge variant="free" label={t("browse.free")} />
                ) : featuredEvent.min_price_ngwee ? (
                  <p className="text-lg font-semibold text-panel-text">
                    {t("detail.fromPrice", { price: formatK(featuredEvent.min_price_ngwee) })}
                  </p>
                ) : null}
                <Link
                  href={`/${locale}/e/${featuredEvent.slug}`}
                  className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-6 text-sm font-semibold text-[var(--primary-btn-fg)] transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {t("browse.viewEvent")}
                </Link>
              </div>
            ) : null}
          </div>

          {featuredEvent?.images[0] ? (
            <CloudinaryImage
              publicId={featuredEvent.images[0]}
              alt={featuredEvent.title}
              width={1200}
              sizes="(max-width: 1024px) 100vw, 52vw"
              ratio="16/9"
              priority
              className="h-full rounded-none"
            />
          ) : (
            <div
              className="min-h-64 bg-gradient-to-br from-primary/30 via-panel-2 to-panel"
              aria-hidden="true"
            />
          )}
        </div>
      </header>

      <section className="flex flex-col gap-6" aria-labelledby="events-results-heading">
        <div className="space-y-1">
          <h2 id="events-results-heading" className="font-display text-h2 text-display-ink">
            {t("browse.title")}
          </h2>
          <p className="text-sm text-text-2">{t("browse.subtitle")}</p>
        </div>

        <div className="rounded-lg border border-border bg-surface p-4 shadow-1 md:p-6">
          <Suspense fallback={null}>
            <DateFilterChips
              labels={filterLabels}
              calendarDates={calendarDates}
              activeDateWindow={dateWindow}
              activeCategory={category}
            />
          </Suspense>
        </div>

        {items.length === 0 ? (
          <EmptyState title={t("browse.emptyTitle")} body={t("browse.emptyBody")} />
        ) : remainingEvents.length > 0 ? (
          <>
            <EventGrid
              items={remainingEvents}
              locale={locale}
              labels={{
                free: t("browse.free"),
                soldOut: t("browse.soldOut"),
                viewEvent: t("browse.viewEvent"),
                capacityTemplate: t("detail.spots", { sold: "{sold}", total: "{total}" }),
                verified: t("browse.verified"),
              }}
            />
            <BackToTop label={tCatalog("plp.backToTop")} />
          </>
        ) : null}
      </section>

      <section
        className="flex flex-col gap-5 rounded-lg border border-border bg-primary-tint px-6 py-8 md:flex-row md:items-center md:justify-between md:px-10"
        aria-labelledby="events-host-cta"
      >
        <div className="max-w-2xl space-y-2">
          <h2 id="events-host-cta" className="font-display text-h2 text-display-ink">
            {t("browse.hostCta")}
          </h2>
          <p className="text-sm leading-relaxed text-text-2">{t("browse.hostPitch")}</p>
        </div>
        <Link
          href={`/${locale}/sell`}
          className="inline-flex min-h-11 shrink-0 items-center justify-center rounded bg-primary px-6 text-sm font-semibold text-[var(--primary-btn-fg)] transition-colors duration-fast hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("browse.hostCta")}
        </Link>
      </section>
    </div>
  );
}
