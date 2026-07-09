"use client";

import { Badge } from "@vergeo/ui/src/badge";
import { EventCard } from "@vergeo/ui/src/event-card";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import Link from "next/link";

export type EventBrowseItem = {
  id: string;
  slug: string;
  title: string;
  venue: string | null;
  images: string[];
  next_starts_at: string | null;
  min_price_ngwee: number | null;
  is_free: boolean;
  spots_sold: number;
  spots_total: number;
  is_sold_out: boolean;
  organiser: {
    display_name: string;
  };
};

type EventGridLabels = {
  free: string;
  soldOut: string;
  viewEvent: string;
  capacityTemplate: string;
};

type EventGridProps = {
  items: EventBrowseItem[];
  locale: string;
  labels: EventGridLabels;
};

function formatCapacity(template: string, sold: number, total: number): string {
  return template.replace("{sold}", String(sold)).replace("{total}", String(total));
}

function formatEventDate(iso: string | null, locale: string): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Africa/Lusaka",
  }).format(date);
}

export function EventGrid({ items, locale, labels }: EventGridProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <ul className="grid list-none gap-4 p-0">
      {items.map((item) => {
        const dateLabel = formatEventDate(item.next_starts_at, locale);
        const venueLabel = item.venue ?? item.organiser.display_name;
        const imagePublicId = item.images[0];

        return (
          <li key={item.id}>
            <Link href={`/${locale}/e/${item.slug}`} className="block">
              <EventCard
                title={item.title}
                dateLabel={dateLabel}
                venueLabel={venueLabel}
                isFree={item.is_free}
                freeLabel={labels.free}
                ngwee={item.is_free ? undefined : (item.min_price_ngwee ?? undefined)}
                spotsFilled={item.spots_sold}
                spotsTotal={item.spots_total}
                capacityLabel={formatCapacity(
                  labels.capacityTemplate,
                  item.spots_sold,
                  item.spots_total,
                )}
                ctaLabel={labels.viewEvent}
                badge={
                  item.is_sold_out ? <Badge variant="sold_out" label={labels.soldOut} /> : undefined
                }
                media={
                  imagePublicId ? (
                    <CloudinaryImage
                      publicId={imagePublicId}
                      alt={item.title}
                      width={720}
                      ratio="16/9"
                    />
                  ) : undefined
                }
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
