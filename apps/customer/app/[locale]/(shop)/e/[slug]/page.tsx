import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import dynamic from "next/dynamic";
import Link from "next/link";
import { cookies } from "next/headers";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { eventAccessCookieName } from "../../../../../lib/event-access";

import { EventJsonLd, isEventIndexable, type EventJsonLdInput } from "./_components/event-jsonld";
import { isPastEventInstance } from "./_lib/instance-time";
import { PrivateEventAccess } from "./_components/private-event-access";

import type { Metadata } from "next";

export const revalidate = 300;

const TicketPicker = dynamic(
  () => import("./_components/ticket-picker").then((mod) => mod.TicketPicker),
  {
    loading: () => (
      <section
        className="min-h-64 rounded-lg border border-border bg-surface p-5 shadow-2"
        aria-busy="true"
      />
    ),
  },
);

type EventInstance = {
  id: string;
  starts_at: string;
  ends_at: string | null;
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
  visibility?: "public" | "unlisted" | "private";
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

async function eventAccessProofFor(slug: string): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(eventAccessCookieName(slug))?.value ?? null;
}

async function fetchEvent(slug: string, accessProof?: string | null): Promise<EventDetail | null> {
  const url = absoluteApiUrl(`/events/${encodeURIComponent(slug)}`);
  if (!url) {
    return null;
  }
  try {
    const response = await fetch(
      url,
      accessProof
        ? {
            cache: "no-store",
            headers: { "X-Event-Access": accessProof },
          }
        : { next: { revalidate, tags: [`event:${slug}`, "events"] } },
    );
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
    <CloudinaryImageStatic
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
  const event = await fetchEvent(slug, await eventAccessProofFor(slug));
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

  const indexable = event.visibility === "public" && isEventIndexable(
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
  const eventAccessProof = await eventAccessProofFor(slug);
  const event = await fetchEvent(slug, eventAccessProof);

  if (!event) {
    return <PrivateEventAccess slug={slug} />;
  }

  const heroImage = event.images[0];
  const featuredInstance =
    event.instances.find((instance) => !isPastEventInstance(instance)) ??
    event.instances[event.instances.length - 1];

  return (
    <article className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 pb-10">
      <EventJsonLd event={toEventJsonLdInput(event, locale)} />

      <Link
        href={`/${locale}/events`}
        className="w-fit text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("browse.title")}
      </Link>

      <header className="relative isolate min-h-[26rem] overflow-hidden rounded-lg bg-panel shadow-2">
        {heroImage ? (
          <CloudinaryImageStatic
            publicId={heroImage}
            alt={event.title}
            width={1440}
            sizes="(max-width: 1400px) 100vw, 1400px"
            ratio="16/9"
            priority
            className="min-h-[26rem] w-full rounded-none"
          />
        ) : (
          <div
            className="absolute inset-0 bg-gradient-to-br from-primary/30 via-panel-2 to-panel"
            aria-hidden="true"
          />
        )}

        <div className="absolute inset-0 flex items-end bg-gradient-to-t from-panel via-panel/60 to-transparent p-6 md:p-10 lg:p-12">
          <div className="max-w-4xl space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {event.is_sold_out ? <Badge variant="sold_out" label={t("detail.soldOut")} /> : null}
              {event.is_free ? <Badge variant="free" label={t("detail.free")} /> : null}
            </div>
            <h1 className="font-display text-hero text-panel-text">{event.title}</h1>
            <div className="flex flex-col gap-1 text-sm text-panel-muted sm:flex-row sm:flex-wrap sm:gap-x-5">
              {featuredInstance ? (
                <p>{formatInstanceDate(featuredInstance.starts_at, locale)}</p>
              ) : null}
              {event.venue ? (
                <p>
                  {event.venue}
                  {event.landmark
                    ? ` · ${t("detail.landmark", { landmark: event.landmark })}`
                    : null}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] lg:gap-12">
        <div className="flex min-w-0 flex-col gap-8">
          {event.description ? (
            <section className="flex flex-col gap-3" aria-labelledby="event-about-heading">
              <h2 id="event-about-heading" className="font-display text-h2 text-display-ink">
                {t("detail.about")}
              </h2>
              <p className="max-w-3xl text-body leading-relaxed text-text-2">{event.description}</p>
            </section>
          ) : null}

          <section className="flex flex-col gap-4" aria-labelledby="event-dates-heading">
            <h2 id="event-dates-heading" className="font-display text-h2 text-display-ink">
              {t("detail.dates")}
            </h2>
            <ol className="flex list-none flex-col gap-3 p-0">
              {event.instances.map((instance, index) => {
                const past = isPastEventInstance(instance);
                return (
                  <li
                    key={instance.id}
                    className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-1 sm:grid-cols-[3rem_minmax(0,1fr)_auto] sm:items-center"
                  >
                    <span className="font-display text-h2 text-primary" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <p className="font-medium text-text">
                        {formatInstanceDate(instance.starts_at, locale)}
                      </p>
                      <p className="mt-1 text-xs text-text-3">
                        {t("detail.spots", {
                          sold: instance.spots_sold,
                          total: instance.capacity,
                        })}
                      </p>
                    </div>
                    {past ? <Badge variant="public" label={t("detail.pastInstance")} /> : null}
                  </li>
                );
              })}
            </ol>
          </section>

          {event.venue || (event.lat !== null && event.lng !== null) ? (
            <section
              className="rounded-lg border border-border bg-bg-2 p-5"
              aria-labelledby="event-venue-heading"
            >
              <h2 id="event-venue-heading" className="font-display text-h3 text-display-ink">
                {t("detail.venue")}
              </h2>
              {event.venue ? (
                <p className="mt-2 text-sm text-text-2">
                  {event.venue}
                  {event.landmark
                    ? ` · ${t("detail.landmark", { landmark: event.landmark })}`
                    : null}
                </p>
              ) : null}
              {event.lat !== null && event.lng !== null ? (
                <Link
                  href={mapsUrl(event.lat, event.lng)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {t("detail.mapHint")}
                </Link>
              ) : null}
            </section>
          ) : null}
        </div>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:h-fit">
          <TicketPicker
            eventSlug={event.slug}
            instances={event.instances}
            ticketTypes={event.ticket_types}
            isSoldOut={event.is_sold_out}
            eventAccessProof={eventAccessProof}
          />

          <section className="rounded-lg border border-border bg-bg-2 p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
              {t("detail.organiser")}
            </p>
            <div className="mt-3 flex items-start gap-3">
              {event.organiser.logo_url ? (
                <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border bg-bg">
                  {organiserLogo(event.organiser.logo_url)}
                </div>
              ) : null}
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-text">{event.organiser.display_name}</p>
                  {event.organiser.preferred_badge ? (
                    <Badge variant="public" label={t("browse.verified")} />
                  ) : null}
                </div>
                {event.organiser.description ? (
                  <p className="mt-1 text-sm text-text-2">{event.organiser.description}</p>
                ) : null}
                {event.organiser.slug ? (
                  <Link
                    href={`/${locale}/v/${event.organiser.slug}`}
                    className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                  >
                    {t("detail.organiserCta")}
                  </Link>
                ) : null}
              </div>
            </div>
          </section>
        </aside>
      </div>
    </article>
  );
}
