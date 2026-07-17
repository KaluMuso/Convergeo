import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import dynamic from "next/dynamic";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { EventJsonLd, isEventIndexable, type EventJsonLdInput } from "./_components/event-jsonld";

import type { Metadata } from "next";

export const revalidate = 300;

const TicketPicker = dynamic(
  () => import("./_components/ticket-picker").then((mod) => mod.TicketPicker),
  {
    loading: () => (
      <section
        className="min-h-24 rounded-lg border border-border bg-surface p-4"
        aria-busy="true"
      />
    ),
  },
);

type EventInstance = {
  id: string;
  starts_at: string;
  ends_at: string;
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
  attendee_named: boolean;
  early_bird_price_ngwee: number | null;
  early_bird_until: string | null;
  tiers: { min_qty: number; price_ngwee: number }[];
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
    logo_url: string | null;
    description: string | null;
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
  const messages = {
    ...baseMessages,
    events: eventsMessages,
  } as AbstractIntlMessages;

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

function organiserLogo(logoUrl: string) {
  if (logoUrl.startsWith("http://") || logoUrl.startsWith("https://")) {
    return (
      <div
        aria-hidden
        className="h-full w-full bg-cover bg-center"
        style={{ backgroundImage: `url(${logoUrl})` }}
      />
    );
  }
  return (
    <CloudinaryImage
      publicId={logoUrl}
      alt=""
      width={96}
      ratio="1/1"
      className="h-full w-full object-cover"
    />
  );
}

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => [{ locale, slug: "zed-summer-festival" }]);
}

function eventImageUrls(images: string[]): string[] {
  return resolveCloudinaryImageUrls(images);
}

function toEventJsonLdInput(event: EventDetail, locale: string): EventJsonLdInput {
  return {
    name: event.title,
    slug: event.slug,
    locale,
    description: event.description,
    venue: event.venue,
    landmark: event.landmark,
    lat: event.lat,
    lng: event.lng,
    imageUrls: eventImageUrls(event.images),
    instances: event.instances.map((instance) => ({
      startsAt: instance.starts_at,
      endsAt: instance.ends_at,
    })),
    ticketTypes: event.ticket_types.map((ticket) => ({
      name: ticket.name,
      priceNgwee: ticket.price_ngwee,
      isFree: ticket.is_free,
      isSoldOut: ticket.is_sold_out,
    })),
    organiserName: event.organiser.display_name,
    isFree: event.is_free,
  };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const event = await fetchEvent(slug);
  const t = await getEventsTranslator(locale);

  if (!event) {
    return {
      title: t("browse.title"),
      robots: { index: false, follow: false },
    };
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

  // Past events whose last instance ended >30d ago drop out of the index.
  const indexable = isEventIndexable(
    event.instances.map((instance) => ({
      startsAt: instance.starts_at,
      endsAt: instance.ends_at,
    })),
  );

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
      images: [
        {
          url: `${buildLocaleCanonical(locale)}/opengraph-image?${ogParams.toString()}`,
        },
      ],
    },
    robots: { index: indexable, follow: true },
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

  return (
    <article className="flex flex-col gap-6 pb-8 lg:mx-auto lg:w-full lg:max-w-5xl">
      <EventJsonLd event={toEventJsonLdInput(event, locale)} />

      {/* Full-image overlay hero — aubergine gradient fallback when there is no image. */}
      <header className="relative overflow-hidden rounded-lg">
        {heroImage ? (
          <CloudinaryImage
            publicId={heroImage}
            alt={event.title}
            width={1280}
            ratio="16/9"
            priority
            className="h-full w-full object-cover"
          />
        ) : (
          <div
            className="aspect-[16/9] w-full bg-gradient-to-br from-panel to-panel-2"
            aria-hidden
          />
        )}
        <div
          className="absolute inset-0 bg-gradient-to-t from-panel via-panel/40 to-transparent"
          aria-hidden
        />
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-2 p-4 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            {event.is_sold_out ? <Badge variant="sold_out" label={t("detail.soldOut")} /> : null}
            {event.is_free ? <Badge variant="free" label={t("detail.free")} /> : null}
          </div>
          <h1 className="font-display text-h1 text-panel-text">{event.title}</h1>
          {event.venue ? (
            <p className="text-sm text-panel-muted">
              {event.venue}
              {event.landmark ? ` · ${t("detail.landmark", { landmark: event.landmark })}` : null}
            </p>
          ) : null}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex flex-col gap-6">
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
                      <p className="font-medium text-text">
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

          {event.lat !== null && event.lng !== null ? (
            <section className="flex flex-col gap-2">
              <h2 className="font-display text-h3 text-display-ink">{t("detail.venue")}</h2>
              <Link
                href={mapsUrl(event.lat, event.lng)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-semibold text-primary underline underline-offset-2"
              >
                {t("detail.mapHint")}
              </Link>
            </section>
          ) : null}

          <section className="rounded-lg border border-border bg-bg-2 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-3">
              {t("detail.organiser")}
            </p>
            <div className="mt-2 flex items-start gap-3">
              {event.organiser.logo_url ? (
                <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border bg-bg">
                  {organiserLogo(event.organiser.logo_url)}
                </div>
              ) : null}
              <div className="min-w-0">
                <p className="font-semibold text-text">{event.organiser.display_name}</p>
                {event.organiser.description ? (
                  <p className="mt-1 text-sm text-text-2">{event.organiser.description}</p>
                ) : null}
                {event.organiser.slug ? (
                  <Link
                    href={`/${locale}/v/${event.organiser.slug}`}
                    className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-primary"
                  >
                    {t("detail.organiserCta")}
                  </Link>
                ) : null}
              </div>
            </div>
          </section>
        </div>

        {/* Sticky ticket sidebar on desktop; stacks below the content on mobile. */}
        <aside className="lg:sticky lg:top-20 lg:h-fit">
          <TicketPicker
            eventSlug={event.slug}
            instances={event.instances}
            ticketTypes={event.ticket_types}
            isSoldOut={event.is_sold_out}
          />
        </aside>
      </div>
    </article>
  );
}
