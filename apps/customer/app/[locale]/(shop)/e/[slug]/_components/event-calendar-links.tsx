import { absoluteApiUrl } from "../../../../../../lib/api-base-url";

export type EventCalendarLinksLabels = {
  heading: string;
  addSingle: string;
  addForDate: string;
};

type EventInstanceLink = {
  id: string;
  starts_at: string;
};

type EventCalendarLinksProps = {
  slug: string;
  instances: EventInstanceLink[];
  locale: string;
  labels: EventCalendarLinksLabels;
};

function formatShortDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    timeZone: "Africa/Lusaka",
  }).format(new Date(iso));
}

function icsUrl(slug: string, instanceId?: string): string | null {
  const base = absoluteApiUrl(`/events/${encodeURIComponent(slug)}/calendar.ics`);
  if (!base) {
    return null;
  }
  if (instanceId) {
    const url = new URL(base);
    url.searchParams.set("instance_id", instanceId);
    return url.toString();
  }
  return base;
}

export function EventCalendarLinks({ slug, instances, locale, labels }: EventCalendarLinksProps) {
  const upcoming = instances.filter(
    (instance) => new Date(instance.starts_at).getTime() > Date.now(),
  );
  if (upcoming.length === 0) {
    return null;
  }

  return (
    <section className="flex flex-col gap-2" aria-labelledby="event-calendar-heading">
      <h2 id="event-calendar-heading" className="font-display text-h3 text-display-ink">
        {labels.heading}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {upcoming.length === 1 ? (
          <li>
            <a
              href={icsUrl(slug) ?? "#"}
              className="inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.addSingle}
            </a>
          </li>
        ) : (
          upcoming.map((instance) => (
            <li key={instance.id}>
              <a
                href={icsUrl(slug, instance.id) ?? "#"}
                className="inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {labels.addForDate.replace("{date}", formatShortDate(instance.starts_at, locale))}
              </a>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
