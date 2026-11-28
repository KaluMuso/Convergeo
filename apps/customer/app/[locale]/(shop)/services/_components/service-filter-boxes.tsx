import { ICON_HUE_LIGHT } from "@vergeo/ui/src/icon-hues";
import { Rail } from "@vergeo/ui/src/rail";
import Link from "next/link";

import { ArchetypeIcon } from "../../s/[slug]/_components/templates/archetype-icon";
import { ARCHETYPE_HUE, parseArchetype } from "../../s/[slug]/_lib/archetypes";
import {
  activeCount,
  areaOptions,
  hrefFor,
  PRICE_BAND_KEYS,
  RATING_OPTIONS,
  withPatch,
  type ServiceFilters,
} from "../_lib/filters";

import { VERTICAL_ARCHETYPE, type ServiceVerticalKey } from "./service-verticals";

export type FilterBoxLabels = {
  heading: string;
  more: string;
  clear: string;
  remove: string;
  results: string;
  area: string;
  areaAll: string;
  areaPlaceholder: string;
  filterSubmit: string;
  price: string;
  priceAny: string;
  priceBands: Record<string, string>;
  rating: string;
  ratingAny: string;
  ratingOptions: Record<string, string>;
  availability: string;
  availabilityAny: string;
  availabilityNow: string;
  all: string;
  categories: Record<string, string>;
};

type Props = {
  locale: string;
  filters: ServiceFilters;
  verticals: readonly string[];
  /** Areas seen in the current results (for the area chips). */
  areas: (string | null)[];
  labels: FilterBoxLabels;
};

function chipClass(active: boolean): string {
  return `inline-flex min-h-11 shrink-0 items-center rounded-pill border px-4 text-sm font-medium transition-colors duration-fast focus-visible:outline-none focus-visible:shadow-focusRing ${
    active
      ? "border-primary bg-primary text-[var(--primary-btn-fg)]"
      : "border-border bg-surface text-text-2 hover:border-primary/40"
  }`;
}

function Box({ title, children, id }: { title: string; children: React.ReactNode; id: string }) {
  return (
    <section
      className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3"
      aria-labelledby={id}
    >
      <h3 id={id} className="m-0 text-xs font-semibold uppercase tracking-wide text-text-3">
        {title}
      </h3>
      <div className="flex flex-wrap gap-2">{children}</div>
    </section>
  );
}

/**
 * Filter boxes for the services listing: vertical cards (archetype-coloured) on top, then
 * boxes for area, price band, rating and availability. Every option is a link, so the
 * state lives in the URL and the page works without client JS.
 */
export function ServiceFilterBoxes({ locale, filters, verticals, areas, labels }: Props) {
  const count = activeCount(filters);
  const link = (patch: Partial<ServiceFilters>) => hrefFor(locale, withPatch(filters, patch));
  const chips: { key: string; label: string; href: string }[] = [];
  if (filters.category) {
    chips.push({
      key: "category",
      label: labels.categories[filters.category] ?? filters.category,
      href: link({ category: null }),
    });
  }
  if (filters.area) chips.push({ key: "area", label: filters.area, href: link({ area: "" }) });
  if (filters.band) {
    chips.push({
      key: "band",
      label: labels.priceBands[filters.band] ?? filters.band,
      href: link({ band: null }),
    });
  }
  if (filters.rating) {
    chips.push({
      key: "rating",
      label: labels.ratingOptions[filters.rating] ?? filters.rating,
      href: link({ rating: null }),
    });
  }
  if (filters.avail) {
    chips.push({
      key: "avail",
      label: labels.availabilityNow,
      href: link({ avail: false }),
    });
  }
  const areaChoices = areaOptions(areas);

  return (
    <div className="flex flex-col gap-3" data-testid="service-filters">
      <Rail className="-mx-1 flex gap-2 px-1 pb-1">
        <Link
          href={link({ category: null })}
          className={chipClass(filters.category === null)}
          aria-current={filters.category === null ? "true" : undefined}
        >
          {labels.all}
        </Link>
        {verticals.map((vertical) => {
          const archetype = parseArchetype(VERTICAL_ARCHETYPE[vertical as ServiceVerticalKey]);
          const hue = ICON_HUE_LIGHT[ARCHETYPE_HUE[archetype]].stroke;
          const active = filters.category === vertical;
          return (
            <Link
              key={vertical}
              href={link({ category: active ? null : vertical })}
              aria-current={active ? "true" : undefined}
              data-testid={`filter-vertical-${vertical}`}
              className="flex min-h-11 shrink-0 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-text transition-colors duration-fast focus-visible:outline-none focus-visible:shadow-focusRing"
              style={{
                borderColor: active ? hue : "var(--border)",
                background: `color-mix(in srgb, ${hue} ${active ? 22 : 8}%, var(--surface))`,
              }}
            >
              <span style={{ color: hue }}>
                <ArchetypeIcon archetype={archetype} className="h-4 w-4" />
              </span>
              {labels.categories[vertical] ?? vertical}
            </Link>
          );
        })}
      </Rail>

      <details className="rounded-lg" open={count > 1 ? true : undefined}>
        <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-pill border border-border bg-surface px-4 text-sm font-semibold text-text focus-visible:outline-none focus-visible:shadow-focusRing">
          {labels.more}
          {count > 0 ? (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs text-[var(--primary-btn-fg)]">
              {count}
            </span>
          ) : null}
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Box id="filter-area" title={labels.area}>
            <Link href={link({ area: "" })} className={chipClass(filters.area === "")}>
              {labels.areaAll}
            </Link>
            {areaChoices.map((area) => (
              <Link
                key={area}
                href={link({ area: filters.area === area ? "" : area })}
                className={chipClass(filters.area === area)}
              >
                {area}
              </Link>
            ))}
            <form action={`/${locale}/services`} method="get" className="flex w-full gap-2">
              {filters.category ? (
                <input type="hidden" name="category" value={filters.category} />
              ) : null}
              {filters.band ? <input type="hidden" name="band" value={filters.band} /> : null}
              {filters.rating ? <input type="hidden" name="rating" value={filters.rating} /> : null}
              {filters.avail ? <input type="hidden" name="avail" value="1" /> : null}
              <input
                name="area"
                defaultValue={filters.area}
                placeholder={labels.areaPlaceholder}
                aria-label={labels.area}
                className="min-h-11 min-w-0 flex-1 rounded-md border border-border bg-surface px-3 text-sm"
              />
              <button
                type="submit"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-semibold"
              >
                {labels.filterSubmit}
              </button>
            </form>
          </Box>

          <Box id="filter-price" title={labels.price}>
            <Link href={link({ band: null })} className={chipClass(filters.band === null)}>
              {labels.priceAny}
            </Link>
            {PRICE_BAND_KEYS.map((band) => (
              <Link
                key={band}
                href={link({ band: filters.band === band ? null : band })}
                className={chipClass(filters.band === band)}
                data-testid={`filter-band-${band}`}
              >
                {labels.priceBands[band]}
              </Link>
            ))}
          </Box>

          <Box id="filter-rating" title={labels.rating}>
            <Link href={link({ rating: null })} className={chipClass(filters.rating === null)}>
              {labels.ratingAny}
            </Link>
            {RATING_OPTIONS.map((option) => (
              <Link
                key={option}
                href={link({
                  rating: filters.rating === option ? null : option,
                })}
                className={chipClass(filters.rating === option)}
                data-testid={`filter-rating-${option}`}
              >
                ★ {labels.ratingOptions[option]}
              </Link>
            ))}
          </Box>

          <Box id="filter-availability" title={labels.availability}>
            <Link href={link({ avail: false })} className={chipClass(!filters.avail)}>
              {labels.availabilityAny}
            </Link>
            <Link
              href={link({ avail: !filters.avail })}
              className={chipClass(filters.avail)}
              data-testid="filter-avail-now"
            >
              {labels.availabilityNow}
            </Link>
          </Box>
        </div>
      </details>

      {chips.length > 0 ? (
        <ul
          className="m-0 flex list-none flex-wrap items-center gap-2 p-0"
          data-testid="active-filters"
        >
          {chips.map((chip) => (
            <li key={chip.key}>
              <Link
                href={chip.href}
                aria-label={labels.remove.replace("{label}", chip.label)}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-pill bg-primary-tint px-3 text-sm font-medium text-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {chip.label}
                <span aria-hidden="true">×</span>
              </Link>
            </li>
          ))}
          <li>
            <Link
              href={`/${locale}/services`}
              className="inline-flex min-h-9 items-center px-2 text-sm font-semibold text-primary underline-offset-4 hover:underline"
            >
              {labels.clear}
            </Link>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
