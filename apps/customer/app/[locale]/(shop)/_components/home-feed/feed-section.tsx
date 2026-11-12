import { EventCard } from "@vergeo/ui/src/event-card";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { ServiceCard } from "@vergeo/ui/src/service-card";
import { VendorCard } from "@vergeo/ui/src/vendor-card";
import Link from "next/link";

import { ListingGrid } from "../plp/listing-grid";

import { AdTracker } from "./ad-tracker";
import {
  localizeHref,
  mapFeedListing,
  resolveSectionTitle,
  type AdCreative,
  type FeedLabels,
  type FeedSection,
} from "./feed-types";

/**
 * One resolved home-feed section. Server- and client-safe (no server-only
 * imports) so the SSR first page and the lazily loaded pages share markup.
 */
type FeedSectionViewProps = {
  section: FeedSection;
  locale: string;
  labels: FeedLabels;
  /** Above-the-fold listings get eager images (first SSR section only). */
  priorityCount?: number;
};

const LUSAKA_TZ = "Africa/Lusaka";

function SectionHeader({
  id,
  title,
  viewAllHref,
  viewAllLabel,
  locale,
  subtitle,
}: {
  id: string;
  title: string;
  viewAllHref: string | null;
  viewAllLabel: string;
  locale: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h2 id={id} className="font-display text-h2 text-display-ink">
          {title}
        </h2>
        {subtitle ? <p className="text-sm text-muted">{subtitle}</p> : null}
      </div>
      {viewAllHref ? (
        <Link
          href={localizeHref(viewAllHref, locale)}
          className="shrink-0 text-sm font-medium text-primary"
        >
          {viewAllLabel}
        </Link>
      ) : null}
    </div>
  );
}

export function FeedAdCard({
  ad,
  locale,
  labels,
  variant = "feed",
}: {
  ad: AdCreative;
  locale: string;
  labels: FeedLabels;
  variant?: "feed" | "carousel";
}) {
  const href = localizeHref(ad.cta_href, locale);
  const sponsoredBy = labels.sponsoredBy.replace("{advertiser}", ad.advertiser_name);
  return (
    <AdTracker placementId={ad.placement_id}>
      <a
        href={href}
        data-ad-click={ad.placement_id}
        {...(ad.external ? { target: "_blank", rel: "sponsored noopener noreferrer" } : {})}
        aria-label={`${labels.sponsored}: ${ad.headline} — ${sponsoredBy}`}
        className="group relative flex flex-col overflow-hidden rounded-lg border border-border bg-surface no-underline shadow-1 sm:flex-row"
      >
        <div className="relative w-full sm:w-2/5">
          <CloudinaryImageStatic
            publicId={ad.image_public_id}
            alt=""
            width={variant === "carousel" ? 960 : 640}
            ratio="16/9"
            sizes="(max-width: 640px) 100vw, 40vw"
            className="h-full w-full object-cover"
          />
          <span className="absolute left-2 top-2 rounded-pill bg-surface px-2 py-0.5 text-xs font-semibold text-text shadow-1">
            {labels.sponsored}
          </span>
        </div>
        <div className="flex flex-1 flex-col justify-center gap-2 p-4">
          <p className="text-xs text-muted">{sponsoredBy}</p>
          <p className="font-display text-h3 text-display-ink">{ad.headline}</p>
          {ad.body ? <p className="text-sm text-muted">{ad.body}</p> : null}
          <span className="text-sm font-semibold text-primary group-hover:underline">
            {ad.cta_label ?? labels.adCta}
          </span>
        </div>
      </a>
    </AdTracker>
  );
}

export function FeedSectionView({
  section,
  locale,
  labels,
  priorityCount = 0,
}: FeedSectionViewProps) {
  const headingId = `home-feed-${section.key}`;

  if (section.section_type === "ad_slot") {
    if (!section.ad) return null;
    return (
      <section
        aria-label={labels.sponsored}
        className="home-rail motion-fade"
        data-feed-section="ad"
      >
        <FeedAdCard ad={section.ad} locale={locale} labels={labels} />
      </section>
    );
  }

  const title = resolveSectionTitle(section, labels);
  if (!title) return null;
  const subtitle =
    section.section_type === "for_you" && section.explanation
      ? section.explanation.basis === "personal"
        ? labels.forYouPersonal
        : labels.forYouTrending
      : undefined;
  const header = (
    <SectionHeader
      id={headingId}
      title={title}
      viewAllHref={section.view_all_href}
      viewAllLabel={labels.viewAll}
      locale={locale}
      subtitle={subtitle}
    />
  );

  if (section.listings.length > 0) {
    return (
      <section
        aria-labelledby={headingId}
        className="home-rail motion-fade flex flex-col gap-3 lg:gap-4"
        data-feed-section={section.key}
      >
        {header}
        <ListingGrid
          locale={locale}
          listings={section.listings.map(mapFeedListing)}
          labels={labels.card}
          priorityCount={priorityCount}
          density="compact"
        />
      </section>
    );
  }

  if (section.services.length > 0) {
    return (
      <section aria-labelledby={headingId} className="home-rail flex flex-col gap-3 lg:gap-4">
        {header}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {section.services.map((service) => (
            <Link
              key={service.id}
              href={`/${locale}/s/${service.slug}`}
              className="min-w-0 no-underline"
            >
              <ServiceCard
                title={service.title}
                providerLabel={labels.provider.replace("{provider}", service.provider.display_name)}
                media={
                  service.portfolio_images[0] ? (
                    <CloudinaryImageStatic
                      publicId={service.portfolio_images[0]}
                      alt={service.title}
                      width={360}
                      ratio="3/2"
                      sizes="(max-width: 360px) 50vw, (max-width: 720px) 33vw, 25vw"
                      className="h-full w-full object-cover"
                    />
                  ) : undefined
                }
                rating={0}
                reviewCount={0}
                noReviewsLabel={labels.noReviews}
                fromNgwee={service.from_price_ngwee ?? undefined}
                fromPriceLabel={service.from_price_ngwee !== null ? labels.fromPrice : undefined}
                ctaLabel={labels.viewService}
              />
            </Link>
          ))}
        </div>
      </section>
    );
  }

  if (section.events.length > 0) {
    const dateFormat = new Intl.DateTimeFormat(
      locale === "bem" || locale === "nya" ? "en" : locale,
      {
        timeZone: LUSAKA_TZ,
        weekday: "short",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      },
    );
    return (
      <section aria-labelledby={headingId} className="home-rail flex flex-col gap-3 lg:gap-4">
        {header}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {section.events.map((event) => (
            <Link
              key={event.id}
              href={`/${locale}/e/${event.slug}`}
              className="min-w-0 no-underline"
            >
              <EventCard
                title={event.title}
                dateLabel={
                  event.next_starts_at ? dateFormat.format(new Date(event.next_starts_at)) : ""
                }
                venueLabel={event.venue ?? ""}
                isFree={event.is_free}
                freeLabel={labels.free}
                ngwee={event.min_price_ngwee ?? undefined}
                spotsFilled={event.spots_sold}
                spotsTotal={event.spots_total}
                capacityLabel={labels.eventCapacity
                  .replace("{filled}", String(event.spots_sold))
                  .replace("{total}", String(event.spots_total))}
                ctaLabel={labels.viewEvent}
                media={
                  event.images[0] ? (
                    <CloudinaryImageStatic
                      publicId={event.images[0]}
                      alt={event.title}
                      width={360}
                      ratio="16/9"
                      className="h-full w-full object-cover"
                    />
                  ) : undefined
                }
              />
            </Link>
          ))}
        </div>
      </section>
    );
  }

  if (section.vendors.length > 0) {
    return (
      <section aria-labelledby={headingId} className="home-rail flex flex-col gap-3 lg:gap-4">
        {header}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {section.vendors.map((vendor) => (
            <Link
              key={vendor.id}
              href={`/${locale}/v/${vendor.slug}`}
              className="min-w-0 no-underline"
            >
              <VendorCard
                name={vendor.display_name}
                categoryLabel={labels.vendorListings}
                locationLabel={vendor.landmark ?? ""}
                trust={
                  vendor.preferred_badge
                    ? "preferred"
                    : vendor.verified
                      ? "id_verified"
                      : "self_listed"
                }
                trustLabel={
                  vendor.preferred_badge
                    ? labels.vendorPreferred
                    : vendor.verified
                      ? labels.vendorVerified
                      : undefined
                }
                stats={[
                  {
                    label: labels.vendorListings,
                    value: String(vendor.listing_count),
                  },
                ]}
                ctaLabel={labels.visitStore}
              />
            </Link>
          ))}
        </div>
      </section>
    );
  }

  return null;
}
