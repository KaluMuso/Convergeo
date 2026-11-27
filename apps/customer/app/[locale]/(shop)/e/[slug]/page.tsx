import { formatK, loadNamespace, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import {
  ARCHETYPE_THEME,
  isEventArchetype,
  sanitiseDetails,
  type EventArchetype,
} from "@vergeo/ui/src/event-archetype";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import {
  buildCanonicalAlternates,
  buildLocaleCanonical,
  resolveCloudinaryImageUrls,
} from "@vergeo/ui/src/seo/json-ld";
import dynamic from "next/dynamic";
import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { eventAccessCookieName } from "../../../../../lib/event-access";
import { ExternalUrlImage } from "../../../../../lib/media/external-url-image";
import { ApiUnavailablePanel } from "../../_components/api-unavailable";
import { fetchEventDetail } from "../../_components/detail-fetch/fetch-event";
import { OtherShopsRail } from "../../_components/elsewhere/other-shops-rail";

import { FactChips } from "./_components/archetype/archetype-blocks";
import {
  ArchetypeBody,
  ArchetypeLead,
  archetypeChips,
} from "./_components/archetype/archetype-body";
import { EventCalendarLinks } from "./_components/event-calendar-links";
import { EventCountdown } from "./_components/event-countdown";
import { EventJsonLd, isEventIndexable, type EventJsonLdInput } from "./_components/event-jsonld";
import { EventRefundPolicy } from "./_components/event-refund-policy";
import { PrivateEventAccess } from "./_components/private-event-access";
import { isPastEventInstance } from "./_lib/instance-time";

import type { Metadata } from "next";

export const revalidate = 300;

const EventPageSticky = dynamic(
  () => import("./_components/event-page-sticky").then((m) => m.EventPageSticky),
  { loading: () => null },
);

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
  perks?: string | null;
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
  platform_fee_payer?: "organiser" | "buyer";
  platform_fee_bps?: number;
  visibility?: "public" | "unlisted" | "private";
  age_restriction?: number | null;
  archetype?: string;
  archetype_details?: unknown;
  refund_policy_key?: string | null;
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
  searchParams: Promise<{ private?: string }>;
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

async function getCatalogTranslator(locale: string) {
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  return createTranslator({
    locale,
    messages: { catalog: catalogMessages },
    namespace: "catalog",
  }) as EventsTranslator;
}

async function loadEvent(slug: string, privateGate: boolean, accessProof: string | null) {
  return fetchEventDetail(slug, { accessProof, privateGate });
}

async function eventAccessProofFor(slug: string): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(eventAccessCookieName(slug))?.value ?? null;
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

function directionsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

function organiserLogo(logoUrl: string, _organiserName: string) {
  if (logoUrl.startsWith("http://") || logoUrl.startsWith("https://")) {
    return (
      <ExternalUrlImage
        src={logoUrl}
        alt=""
        className="h-full w-full object-cover"
        width={96}
        height={96}
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
  return [];
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

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const query = await searchParams;
  const privateGate =
    query.private === "1" || Boolean((await cookies()).get(eventAccessCookieName(slug)));
  const eventResult = await loadEvent(slug, privateGate, await eventAccessProofFor(slug));
  const t = await getEventsTranslator(locale);

  if (eventResult.kind !== "event") {
    return {
      title: t("browse.title"),
      robots: { index: false, follow: false },
    };
  }

  const event = eventResult.data as EventDetail;
  const description = t("detail.metaDescription", {
    title: event.title,
    venue: event.venue ?? event.organiser.display_name,
  });
  const canonicalPath = buildLocaleCanonical(locale, "e", event.slug);
  const ogParams = new URLSearchParams({ name: event.title });
  if (!event.is_free && event.min_price_ngwee) {
    ogParams.set("price", formatK(event.min_price_ngwee));
  }

  const indexable =
    event.visibility === "public" &&
    isEventIndexable(
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
    twitter: {
      card: "summary_large_image",
      title: event.title,
      description,
    },
    robots: { index: indexable, follow: true },
  };
}

export default async function EventDetailPage({ params, searchParams }: PageProps) {
  const { locale, slug } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const cookieStore = await cookies();
  const privateGate =
    query.private === "1" || Boolean(cookieStore.get(eventAccessCookieName(slug)));
  const [t, tCatalog, eventAccessProof] = await Promise.all([
    getEventsTranslator(locale),
    getCatalogTranslator(locale),
    eventAccessProofFor(slug),
  ]);
  const eventResult = await loadEvent(slug, privateGate, eventAccessProof);
  if (eventResult.kind === "private_access") return <PrivateEventAccess slug={slug} />;
  if (eventResult.kind === "not_found") notFound();
  if (eventResult.kind === "unavailable") {
    return (
      <ApiUnavailablePanel
        retryHref={`/${locale}/e/${encodeURIComponent(slug)}`}
        labels={{
          title: tCatalog("pdp.unavailableTitle"),
          body: tCatalog("pdp.unavailableBody"),
          retry: tCatalog("pdp.unavailableRetry"),
        }}
        testId="event-unavailable"
      />
    );
  }
  const event = eventResult.data as EventDetail;
  const stickyPriceLine = event.is_free
    ? t("detail.free")
    : event.min_price_ngwee
      ? t("detail.fromPrice", { price: formatK(event.min_price_ngwee) })
      : t("detail.getTickets");

  const archetype: EventArchetype = isEventArchetype(event.archetype) ? event.archetype : "generic";
  const theme = ARCHETYPE_THEME[archetype];
  const details = sanitiseDetails(event.archetype_details);
  const heroChips = archetypeChips(details, t);
  const heroImage = event.images[0];
  const featuredInstance =
    event.instances.find((instance) => !isPastEventInstance(instance)) ??
    event.instances[event.instances.length - 1];

  return (
    <article
      className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 pb-28 lg:pb-10"
      data-archetype={archetype}
      style={
        {
          "--arch-tint": theme.tint,
          "--arch-accent": theme.accent,
        } as React.CSSProperties
      }
    >
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
            style={
              archetype === "generic"
                ? undefined
                : {
                    backgroundImage:
                      "linear-gradient(135deg, var(--arch-tint), var(--panel-2) 70%, var(--panel))",
                  }
            }
            aria-hidden="true"
          />
        )}

        <div className="absolute inset-0 flex items-end bg-gradient-to-t from-panel via-panel/80 to-transparent p-6 md:p-10 lg:p-12">
          <div className="max-w-4xl space-y-4">
            {archetype !== "generic" ? (
              <p
                className="w-fit border-l-4 pl-3 text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted"
                style={{ borderColor: "var(--arch-accent)" }}
                data-testid="archetype-kicker"
              >
                {t(`archetype.names.${archetype}`)}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              {event.is_sold_out ? <Badge variant="sold_out" label={t("detail.soldOut")} /> : null}
              {event.is_free ? <Badge variant="free" label={t("detail.free")} /> : null}
              {event.age_restriction ? (
                <Badge
                  variant="public"
                  label={t("detail.ageLimit", { age: event.age_restriction })}
                />
              ) : null}
            </div>
            <h1 className="font-display text-hero text-panel-text">{event.title}</h1>
            <FactChips chips={heroChips} />
            <div className="flex flex-col gap-1 text-sm text-panel-muted sm:flex-row sm:flex-wrap sm:gap-x-5">
              {featuredInstance ? (
                <>
                  <p>{formatInstanceDate(featuredInstance.starts_at, locale)}</p>
                  <EventCountdown
                    startsAt={featuredInstance.starts_at}
                    endsAt={featuredInstance.ends_at}
                    locale={locale}
                    labels={{
                      ended: t("detail.countdown.ended"),
                      today: t("detail.countdown.today"),
                      tomorrow: t("detail.countdown.tomorrow"),
                      days: t("detail.countdown.days"),
                    }}
                  />
                </>
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

      <ArchetypeLead archetype={archetype} rawDetails={event.archetype_details} t={t} />

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

          <ArchetypeBody
            archetype={archetype}
            rawDetails={event.archetype_details}
            images={event.images}
            title={event.title}
            tickets={event.ticket_types.map((ticket) => ({
              id: ticket.id,
              name: ticket.name,
              price_ngwee: ticket.price_ngwee,
              is_free: ticket.is_free,
              is_sold_out: ticket.is_sold_out,
              qty_cap: ticket.qty_cap,
              tickets_sold: ticket.tickets_sold,
              perks: ticket.perks,
              early_bird_price_ngwee: ticket.early_bird_price_ngwee,
            }))}
            t={t}
          />

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

          <EventCalendarLinks
            slug={event.slug}
            instances={event.instances}
            locale={locale}
            labels={{
              heading: t("detail.calendar.heading"),
              addSingle: t("detail.calendar.addSingle"),
              addForDate: t("detail.calendar.addForDate"),
            }}
          />

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
                  href={directionsUrl(event.lat, event.lng)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                  data-testid="event-directions"
                >
                  {t("detail.directions")}
                </Link>
              ) : null}
            </section>
          ) : null}
        </div>

        <aside className="order-first flex flex-col gap-4 lg:order-none lg:sticky lg:top-24 lg:h-fit">
          <EventRefundPolicy
            refundPolicyKey={event.refund_policy_key}
            labels={{
              heading: t("detail.refund.heading"),
              platform_standard: t("detail.refund.platform_standard"),
              no_refunds: t("detail.refund.no_refunds"),
              flexible: t("detail.refund.flexible"),
              unknown: t("detail.refund.unknown"),
            }}
          />
          <div id="tickets" className="scroll-mt-24">
            <TicketPicker
              eventSlug={event.slug}
              instances={event.instances}
              ticketTypes={event.ticket_types}
              isSoldOut={event.is_sold_out}
              eventAccessProof={eventAccessProof}
              platformFeePayer={event.platform_fee_payer === "buyer" ? "buyer" : "organiser"}
              platformFeeBps={event.platform_fee_bps ?? null}
            />
          </div>

          <section className="rounded-lg border border-border bg-bg-2 p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
              {t("detail.organiser")}
            </p>
            <div className="mt-3 flex items-start gap-3">
              {event.organiser.logo_url ? (
                <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full border border-border bg-bg">
                  {organiserLogo(event.organiser.logo_url, event.organiser.display_name)}
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

      {/* Founder rule: related items from OTHER shops, not only this one. */}
      {event.organiser.slug && event.visibility !== "private" ? (
        <Suspense fallback={null}>
          <OtherShopsRail
            locale={locale}
            vendorSlug={event.organiser.slug}
            lead="event"
            excludeIds={[event.id]}
          />
        </Suspense>
      ) : null}
      <EventPageSticky
        priceLine={stickyPriceLine}
        isSoldOut={event.is_sold_out}
        isFree={event.is_free}
        labels={{
          ariaLabel: t("detail.stickyCta.ariaLabel"),
          cta: t("detail.getTickets"),
          free: t("detail.free"),
          soldOut: t("detail.soldOut"),
        }}
      />
    </article>
  );
}
