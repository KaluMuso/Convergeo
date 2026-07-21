import { EventCard } from "@vergeo/ui/src/event-card";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";

import type { MerchSlotRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type EventItem = {
  key: string;
  title: string;
  dateLabel: string;
  venueLabel: string;
  href: string;
  imagePublicId?: string;
  isFree: boolean;
  ngwee?: number;
  spotsFilled: number;
  spotsTotal: number;
};

function parseEventItems(payload: Record<string, unknown>, locale: string): EventItem[] {
  const rawItems = payload.events;
  if (!Array.isArray(rawItems)) {
    return [];
  }

  return rawItems.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }

    const record = entry as Record<string, unknown>;
    const title = typeof record.title === "string" ? record.title : undefined;
    const dateLabel = typeof record.date_label === "string" ? record.date_label : undefined;
    const venueLabel = typeof record.venue_label === "string" ? record.venue_label : undefined;

    if (!title || !dateLabel || !venueLabel) {
      return [];
    }

    return [
      {
        key: typeof record.key === "string" ? record.key : `event-${index}`,
        title,
        dateLabel,
        venueLabel,
        href: typeof record.href === "string" ? record.href : `/${locale}/events`,
        imagePublicId:
          typeof record.image_public_id === "string" ? record.image_public_id : undefined,
        isFree: record.is_free === true,
        ngwee: typeof record.ngwee === "number" ? record.ngwee : undefined,
        spotsFilled: typeof record.spots_filled === "number" ? record.spots_filled : 0,
        spotsTotal: typeof record.spots_total === "number" ? record.spots_total : 0,
      },
    ];
  });
}

type EventsRowProps = {
  slot?: MerchSlotRow;
  locale: string;
  t: CatalogTranslator;
};

export function EventsRow({ slot, locale, t }: EventsRowProps) {
  const items = slot ? parseEventItems(slot.payload, locale) : [];

  if (items.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="home-events-heading" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 id="home-events-heading" className="font-display text-h2 text-display-ink">
          {t("home.events.title")}
        </h2>
        <Link href={`/${locale}/events`} className="min-h-11 text-sm font-semibold text-primary">
          {t("home.events.viewAll")}
        </Link>
      </div>
      <ul className="grid list-none gap-3 p-0">
        {items.map((item) => (
          <li key={item.key}>
            <Link href={item.href} className="block">
              <EventCard
                title={item.title}
                dateLabel={item.dateLabel}
                venueLabel={item.venueLabel}
                isFree={item.isFree}
                freeLabel={t("home.events.free")}
                ngwee={item.ngwee}
                spotsFilled={item.spotsFilled}
                spotsTotal={item.spotsTotal}
                capacityLabel={t("home.events.capacity", {
                  filled: item.spotsFilled,
                  total: item.spotsTotal,
                })}
                ctaLabel={t("home.events.cta")}
                media={
                  item.imagePublicId ? (
                    <CloudinaryImageStatic
                      publicId={item.imagePublicId}
                      alt={item.title}
                      width={720}
                      ratio="16/9"
                    />
                  ) : undefined
                }
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
