import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { browseCardGridClass } from "@vergeo/ui/src/browse-grid";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";

import { ArchetypeIcon } from "../../s/[slug]/_components/templates/archetype-icon";
import { parseArchetype, vibeStyle } from "../../s/[slug]/_lib/archetypes";

export type ServiceBrowseItem = {
  id: string;
  slug: string;
  title: string;
  category: string;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  is_free?: boolean;
  portfolio_images: string[];
  archetype?: string;
  availability?: "available" | "limited" | "unavailable";
  rating_avg?: number | null;
  rating_count?: number;
  provider: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    response_time_tier: "fast" | "same_day" | "slow" | null;
  };
};

type ServiceGridProps = {
  items: ServiceBrowseItem[];
  locale: string;
  labels: {
    viewService: string;
    fromPrice: string;
    askForQuote: string;
    badges: Record<string, string>;
    preferredBadge: string;
    free?: string;
    fullyBooked?: string;
    /** Template with `{rating}` and `{count}` placeholders. */
    ratingLine?: string;
    archetypes?: Record<string, string>;
  };
};

function badgeVariant(tier: ServiceBrowseItem["provider"]["response_time_tier"]) {
  if (tier === "fast") {
    return "free" as const;
  }
  if (tier === "same_day") {
    return "public" as const;
  }
  return "new" as const;
}

export function ServiceGrid({ items, locale, labels }: ServiceGridProps) {
  return (
    <ul className={`motion-fade list-none p-0 ${browseCardGridClass}`}>
      {items.map((item) => {
        const hero = item.portfolio_images[0];
        const tier = item.provider.response_time_tier;
        const archetype = parseArchetype(item.archetype);
        const archetypeLabel = labels.archetypes?.[archetype];
        return (
          <li key={item.id}>
            <Link
              href={`/${locale}/s/${item.slug}`}
              className="group tap flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface transition-[box-shadow,border-color] duration-[250ms] ease-std hover:border-primary/40 hover:shadow-2 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {hero ? (
                <CloudinaryImageStatic
                  publicId={hero}
                  alt={item.title}
                  width={480}
                  ratio="4/3"
                  sizes="(max-width: 640px) 100vw, (max-width: 1100px) 50vw, 33vw"
                  className="w-full rounded-none transition-transform duration-slow ease-std group-hover:scale-[1.03] motion-reduce:transform-none"
                />
              ) : (
                <div
                  className="flex aspect-[4/3] w-full items-center justify-center bg-gradient-to-br from-[var(--vibe-strong)] to-[var(--vibe-tint)] text-[var(--vibe)]"
                  style={vibeStyle(archetype)}
                  aria-hidden="true"
                >
                  <ArchetypeIcon archetype={archetype} className="h-10 w-10" />
                </div>
              )}
              <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  {archetypeLabel ? (
                    <span
                      className="inline-flex min-h-6 items-center gap-1 rounded-pill bg-[var(--vibe-strong)] px-2 text-xs font-semibold text-text"
                      style={vibeStyle(archetype)}
                    >
                      <ArchetypeIcon archetype={archetype} className="h-3 w-3" />
                      {archetypeLabel}
                    </span>
                  ) : null}
                  {item.availability === "unavailable" && labels.fullyBooked ? (
                    <Badge variant="new" label={labels.fullyBooked} />
                  ) : null}
                  {item.is_free && labels.free ? (
                    <Badge variant="free" label={labels.free} />
                  ) : null}
                  {tier ? (
                    <Badge variant={badgeVariant(tier)} label={labels.badges[tier] ?? tier} />
                  ) : null}
                  {item.provider.preferred_badge ? (
                    <Badge variant="public" label={labels.preferredBadge} />
                  ) : null}
                </div>
                <h3 className="m-0 line-clamp-2 font-display text-h3 font-semibold text-display-ink">
                  {item.title}
                </h3>
                {/* Provider line: monogram + name, then service area with a pin. */}
                <p className="m-0 flex items-center gap-2 text-sm text-text-2">
                  <span
                    aria-hidden
                    className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-tint font-display text-xs font-bold text-primary"
                  >
                    {item.provider.display_name.charAt(0)}
                  </span>
                  <span className="truncate">{item.provider.display_name}</span>
                </p>
                {item.service_area ? (
                  <p className="m-0 flex items-center gap-1.5 text-sm text-text-3">
                    <svg
                      aria-hidden
                      viewBox="0 0 24 24"
                      className="h-4 w-4 shrink-0"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
                      <circle cx="12" cy="10" r="2.3" />
                    </svg>
                    <span className="truncate">{item.service_area}</span>
                  </p>
                ) : null}
                {item.rating_avg && labels.ratingLine ? (
                  <p className="m-0 text-sm text-text-2" data-testid="service-rating">
                    <span aria-hidden="true">★ </span>
                    {labels.ratingLine
                      .replace("{rating}", item.rating_avg.toFixed(1))
                      .replace("{count}", String(item.rating_count ?? 0))}
                  </p>
                ) : null}
                <div className="mt-auto flex items-end justify-between gap-2 pt-2">
                  <p className="m-0 font-display text-body font-bold text-text">
                    {item.is_free && labels.free
                      ? labels.free
                      : item.from_price_ngwee
                        ? labels.fromPrice.replace("{price}", formatK(item.from_price_ngwee))
                        : labels.askForQuote}
                  </p>
                  <span className="inline-flex min-h-9 shrink-0 items-center rounded-pill bg-primary-tint px-3 text-sm font-semibold text-primary-deep group-hover:bg-primary group-hover:text-[var(--primary-btn-fg)]">
                    {labels.viewService}
                  </span>
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
