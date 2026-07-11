import {
  buildAbsoluteUrl,
  buildLocaleCanonical,
  JsonLdScript,
  ngweeToZmwDecimal,
} from "@vergeo/ui/src/seo/json-ld";

/**
 * Events SEO — schema.org/Event JSON-LD + indexing policy (M10-P09).
 *
 * Reuses the shared SEO primitives (`ngweeToZmwDecimal`, `buildAbsoluteUrl`,
 * `buildLocaleCanonical`) and builds the Event object locally so this component
 * owns the events discovery shape. No client JS — emitted as inline ld+json.
 */

/** Instances carry only a start time; assume a default duration for `endDate`. */
const EVENT_DURATION_MS = 2 * 60 * 60 * 1000;

/** A past event stays indexable for this grace window after its last instance. */
export const EVENT_NOINDEX_GRACE_DAYS = 30;
const GRACE_MS = EVENT_NOINDEX_GRACE_DAYS * 24 * 60 * 60 * 1000;

export type EventJsonLdInstance = {
  startsAt: string;
};

export type EventJsonLdTicket = {
  name: string;
  priceNgwee: number;
  isFree: boolean;
  isSoldOut: boolean;
};

export type EventJsonLdInput = {
  name: string;
  slug: string;
  locale: string;
  description?: string | null;
  venue?: string | null;
  landmark?: string | null;
  lat?: number | null;
  lng?: number | null;
  imageUrls?: string[];
  instances: EventJsonLdInstance[];
  ticketTypes: EventJsonLdTicket[];
  organiserName: string;
  isFree: boolean;
};

function sortByStart(instances: EventJsonLdInstance[]): EventJsonLdInstance[] {
  return [...instances].sort(
    (left, right) => new Date(left.startsAt).getTime() - new Date(right.startsAt).getTime(),
  );
}

/** Millis of the last-starting instance, or null when the event has none. */
export function latestInstanceStart(instances: EventJsonLdInstance[]): number | null {
  const times = instances
    .map((instance) => new Date(instance.startsAt).getTime())
    .filter((time) => Number.isFinite(time));
  return times.length > 0 ? Math.max(...times) : null;
}

/**
 * An event is indexable unless ALL its instances ended more than the grace
 * window ago (past-but-recent events stay indexable). Eventless events index.
 */
export function isEventIndexable(
  instances: EventJsonLdInstance[],
  now: number = Date.now(),
): boolean {
  const latest = latestInstanceStart(instances);
  if (latest === null) {
    return true;
  }
  return latest + EVENT_DURATION_MS >= now - GRACE_MS;
}

/**
 * schema.org Offer[] for the event. Free events emit a single zero-price offer;
 * paid events emit one offer per priced ticket type with SoldOut/InStock. Price
 * is exact ZMW decimal via `ngweeToZmwDecimal` — never float.
 */
export function buildEventOffers(
  input: EventJsonLdInput,
  pageUrl: string,
): Record<string, unknown>[] {
  if (input.isFree) {
    return [
      {
        "@type": "Offer",
        price: "0",
        priceCurrency: "ZMW",
        availability: "https://schema.org/InStock",
        url: pageUrl,
      },
    ];
  }

  return input.ticketTypes
    .filter((ticket) => !ticket.isFree)
    .map((ticket) => ({
      "@type": "Offer",
      name: ticket.name,
      price: ngweeToZmwDecimal(ticket.priceNgwee),
      priceCurrency: "ZMW",
      availability: ticket.isSoldOut ? "https://schema.org/SoldOut" : "https://schema.org/InStock",
      url: pageUrl,
    }));
}

export function buildEventJsonLd(input: EventJsonLdInput): Record<string, unknown> {
  const pageUrl = buildAbsoluteUrl(buildLocaleCanonical(input.locale, "e", input.slug));
  const sorted = sortByStart(input.instances);
  const primary = sorted[0];
  const offers = buildEventOffers(input, pageUrl);

  const location =
    input.venue || input.landmark
      ? {
          "@type": "Place",
          ...(input.venue ? { name: input.venue } : {}),
          ...(input.landmark
            ? {
                address: {
                  "@type": "PostalAddress",
                  streetAddress: input.landmark,
                  addressLocality: "Lusaka",
                  addressCountry: "ZM",
                },
              }
            : {}),
          ...(input.lat != null && input.lng != null
            ? {
                geo: {
                  "@type": "GeoCoordinates",
                  latitude: input.lat,
                  longitude: input.lng,
                },
              }
            : {}),
        }
      : undefined;

  return {
    "@context": "https://schema.org",
    "@type": "Event",
    name: input.name,
    url: pageUrl,
    eventStatus: "https://schema.org/EventScheduled",
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    ...(input.description ? { description: input.description } : {}),
    ...(primary
      ? {
          startDate: primary.startsAt,
          endDate: new Date(new Date(primary.startsAt).getTime() + EVENT_DURATION_MS).toISOString(),
        }
      : {}),
    ...(input.imageUrls && input.imageUrls.length > 0 ? { image: input.imageUrls } : {}),
    ...(location ? { location } : {}),
    organizer: {
      "@type": "Organization",
      name: input.organiserName,
    },
    performer: {
      "@type": "Organization",
      name: input.organiserName,
    },
    ...(offers.length > 0 ? { offers: offers.length === 1 ? offers[0] : offers } : {}),
  };
}

export function EventJsonLd({ event }: { event: EventJsonLdInput }) {
  return <JsonLdScript data={buildEventJsonLd(event)} />;
}
