import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";

export type ServiceBrowseItem = {
  id: string;
  slug: string;
  title: string;
  category: string;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  portfolio_images: string[];
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
  };
};

function badgeVariant(
  tier: ServiceBrowseItem["provider"]["response_time_tier"],
) {
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
    <ul className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {items.map((item) => {
        const hero = item.portfolio_images[0];
        const tier = item.provider.response_time_tier;
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
                <div className="aspect-[4/3] w-full bg-bg-2" />
              )}
              <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  {tier ? (
                    <Badge
                      variant={badgeVariant(tier)}
                      label={labels.badges[tier] ?? tier}
                    />
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
                <div className="mt-auto flex items-end justify-between gap-2 pt-2">
                  <p className="m-0 font-display text-body font-bold text-text">
                    {item.from_price_ngwee
                      ? labels.fromPrice.replace(
                          "{price}",
                          formatK(item.from_price_ngwee),
                        )
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
