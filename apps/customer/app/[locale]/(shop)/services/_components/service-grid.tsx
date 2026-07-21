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
    <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2">
      {items.map((item) => {
        const hero = item.portfolio_images[0];
        const tier = item.provider.response_time_tier;
        return (
          <li key={item.id}>
            <Link
              href={`/${locale}/s/${item.slug}`}
              className="tap flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface transition-shadow duration-fast ease-std hover:shadow-2"
            >
              {hero ? (
                <CloudinaryImageStatic
                  publicId={hero}
                  alt={item.title}
                  width={480}
                  ratio="4/3"
                  className="w-full"
                />
              ) : (
                <div className="aspect-[4/3] w-full bg-bg-2" />
              )}
              <div className="flex flex-1 flex-col gap-2 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  {tier ? (
                    <Badge variant={badgeVariant(tier)} label={labels.badges[tier] ?? tier} />
                  ) : null}
                  {item.provider.preferred_badge ? (
                    <Badge variant="public" label={labels.preferredBadge} />
                  ) : null}
                </div>
                <h2 className="font-display text-h3 text-display-ink">{item.title}</h2>
                <p className="text-sm text-text-2">{item.provider.display_name}</p>
                {item.service_area ? (
                  <p className="text-xs text-text-3">{item.service_area}</p>
                ) : null}
                <p className="mt-auto text-sm font-semibold text-text">
                  {item.from_price_ngwee
                    ? labels.fromPrice.replace("{price}", formatK(item.from_price_ngwee))
                    : labels.askForQuote}
                </p>
                <span className="text-sm font-semibold text-primary">{labels.viewService}</span>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
