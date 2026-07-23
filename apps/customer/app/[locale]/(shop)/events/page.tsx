import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { PanelHero } from "@vergeo/ui/src/panel-hero";
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
    <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <PanelHero
        title={t("browse.title")}
        subtitle={t("browse.subtitle")}
        cta={{
          href: `/${locale}/sell`,
          label: t("browse.hostCta"),
          pitch: t("browse.hostPitch"),
          LinkComponent: Link,
        }}
      />

      <Suspense fallback={null}>
        <DateFilterChips
          labels={filterLabels}
          calendarDates={calendarDates}
          activeDateWindow={dateWindow}
          activeCategory={category}
        />
      </Suspense>

      {items.length === 0 ? (
        <EmptyState title={t("browse.emptyTitle")} body={t("browse.emptyBody")} />
      ) : (
        <>
          <EventGrid
            items={items}
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
      )}
    </div>
  );
}
