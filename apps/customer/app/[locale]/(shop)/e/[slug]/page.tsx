import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { Button } from "@vergeo/ui/src/button";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { PriceBlock } from "@vergeo/ui/src/price-block";
import {
  buildCanonicalAlternates,
  buildEventJsonLd,
  buildLocaleCanonical,
  JsonLdScript,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

export const revalidate = 300;

type EventInstance = {
  id: string;
  starts_at: string;
  capacity: number;
  spots_sold: number;
  spots_remaining: number;
  is_sold_out: boolean;
};

type TicketType = {
  id: string;
  kind: "fixed" | "tier" | "free_rsvp";
  name: string;
  price_ngwee: number;
  qty_cap: number | null;
  tickets_sold: number;
  is_sold_out: boolean;
  is_free: boolean;
};

type EventDetail = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  venue: string | null;
  lat: number | null;
  lng: number | null;
  landmark: string | null;
  images: string[];
  instances: EventInstance[];
  ticket_types: TicketType[];
  min_price_ngwee: number | null;
  is_free: boolean;
  is_sold_out: boolean;
  organiser: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    landmark: string | null;
  };
};

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

type EventsTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
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

async function fetchEvent(slug: string): Promise<EventDetail | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/events/${encodeURIComponent(slug)}`, {
      next: { revalidate, tags: [`event:${slug}`, "events"] },
    });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as EventDetail;
  } catch {
    return null;
  }
}

function formatInstanceDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Africa/Lusaka",
  }).format(new Date(iso));
}

function isPastInstance(iso: string): boolean {
  return new Date(iso).getTime() < Date.now();
}

function mapsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
}

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => [{ locale, slug: "zed-summer-festival" }]);
}

function eventImageUrls(images: string[]): string[] {
  return resolveCloudinaryImageUrls(images);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const event = await fetchEvent(slug);
  const t = await getEventsTranslator(locale);

  if (!event) {
    return { title: t("browse.title"), robots: { index: false, follow: false } };
  }

  const description = t("detail.metaDescription", {
    title: event.title,
    venue: event.venue ?? event.organiser.display_name,
  });
  const canonicalPath = buildLocaleCanonical(locale, "e", event.slug);
  const ogParams = new URLSearchParams({ name: event.title });
  if (!event.is_free && event.min_price_ngwee) {
    ogParams.set("price", formatK(event.min_price_ngwee));
  }

  return {
    title: t("detail.metaTitle", { title: event.title }),
    description,
    alternates: buildCanonicalAlternates(locale, "e", event.slug),
    openGraph: {
      title: event.title,
      description,
      type: "website",
      locale,
      url: canonicalPath,
      images: [{ url: `${buildLocaleCanonical(locale)}/opengraph-image?${ogParams.toString()}` }],
    },
    robots: { index: true, follow: true },
  };
}

export default async function EventDetailPage({ params }: PageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);

  const t = await getEventsTranslator(locale);
  const event = await fetchEvent(slug);

  if (!event) {
    notFound();
  }

  const heroImage = event.images[0];
  const jsonLd = buildEventJsonLd({
    name: event.title,
    slug: event.slug,
    locale,
    description: event.description,
    venue: event.venue,
    landmark: event.landmark,
    lat: event.lat,
    lng: event.lng,
    imageUrls: eventImageUrls(event.images),
    instances: event.instances.map((instance) => ({ startsAt: instance.starts_at })),
    ticketTypes: event.ticket_types.map((ticket) => ({
      name: ticket.name,
      priceNgwee: ticket.price_ngwee,
      isFree: ticket.is_free,
      isSoldOut: ticket.is_sold_out,
    })),
    organiserName: event.organiser.display_name,
    isFree: event.is_free,
  });

  return (
    <article className="flex flex-col gap-6 pb-8">
      <JsonLdScript data={jsonLd} />
      <header className="flex flex-col gap-3">
        {heroImage ? (
          <div className="overflow-hidden rounded-lg border border-border">
            <CloudinaryImage
              publicId={heroImage}
              alt={event.title}
              width={960}
              ratio="16/9"
              priority
            />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {event.is_sold_out ? <Badge variant="sold_out" label={t("detail.soldOut")} /> : null}
          {event.is_free ? <Badge variant="free" label={t("detail.free")} /> : null}
        </div>
        <h1 className="font-display text-h1 text-display-ink">{event.title}</h1>
        {event.venue ? (
          <p className="text-sm text-text-2">
            {event.venue}
            {event.landmark ? ` · ${t("detail.landmark", { landmark: event.landmark })}` : null}
          </p>
        ) : null}
      </header>

      {event.description ? (
        <section className="flex flex-col gap-2">
          <h2 className="font-display text-h3 text-display-ink">{t("detail.about")}</h2>
          <p className="text-sm leading-relaxed text-text-2">{event.description}</p>
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-h3 text-display-ink">{t("detail.dates")}</h2>
        <ul className="flex list-none flex-col gap-2 p-0">
          {event.instances.map((instance) => {
            const past = isPastInstance(instance.starts_at);
            return (
              <li
                key={instance.id}
                className="rounded-lg border border-border bg-surface px-4 py-3 text-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-text-1">
                    {formatInstanceDate(instance.starts_at, locale)}
                  </p>
                  {past ? <Badge variant="public" label={t("detail.pastInstance")} /> : null}
                </div>
                <p className="mt-1 text-text-3">
                  {t("detail.spots", {
                    sold: instance.spots_sold,
                    total: instance.capacity,
                  })}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-h3 text-display-ink">{t("detail.tickets")}</h2>
        <ul className="flex list-none flex-col gap-3 p-0">
          {event.ticket_types.map((ticket) => (
            <li
              key={ticket.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3"
            >
              <div className="min-w-0">
                <p className="font-semibold text-text-1">{ticket.name}</p>
                {ticket.qty_cap !== null ? (
                  <p className="text-xs text-text-3">
                    {t("detail.ticketRemaining", {
                      count: Math.max(ticket.qty_cap - ticket.tickets_sold, 0),
                    })}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {ticket.is_free ? (
                  <span className="text-sm font-bold text-success">{t("detail.free")}</span>
                ) : (
                  <PriceBlock ngwee={ticket.price_ngwee} />
                )}
                {ticket.is_sold_out ? (
                  <span className="text-xs font-semibold text-danger">{t("detail.soldOut")}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
        {!event.is_free && event.min_price_ngwee ? (
          <p className="text-sm text-text-2">
            {t("detail.fromPrice", { price: formatK(event.min_price_ngwee) })}
          </p>
        ) : null}
        <Button
          type="button"
          variant="primary"
          disabled
          aria-disabled
          loading={false}
          loadingLabel={t("detail.getTicketsSoon")}
          className="w-full"
        >
          {t("detail.getTicketsSoon")}
        </Button>
        <p className="text-center text-xs text-text-3">{t("detail.getTickets")}</p>
      </section>

      {event.lat !== null && event.lng !== null ? (
        <section className="flex flex-col gap-2">
          <h2 className="font-display text-h3 text-display-ink">{t("detail.venue")}</h2>
          <Link
            href={mapsUrl(event.lat, event.lng)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-primary"
          >
            {t("detail.mapHint")}
          </Link>
        </section>
      ) : null}

      <section className="rounded-lg border border-border bg-bg-2 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-3">
          {t("detail.organiser")}
        </p>
        <p className="mt-1 font-semibold text-text-1">{event.organiser.display_name}</p>
        {event.organiser.slug ? (
          <Link
            href={`/${locale}/v/${event.organiser.slug}`}
            className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-primary"
          >
            {t("detail.organiserCta")}
          </Link>
        ) : null}
      </section>
    </article>
  );
}
