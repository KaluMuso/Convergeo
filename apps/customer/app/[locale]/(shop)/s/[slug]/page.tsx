import { formatK, loadNamespace, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { cldUrl } from "@vergeo/ui/src/media/cloudinary-url";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import { buildSocialMetadata } from "@vergeo/ui/src/seo/metadata";
import dynamic from "next/dynamic";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { ApiUnavailablePanel } from "../../_components/api-unavailable";
import { fetchServiceDetail } from "../../_components/detail-fetch/fetch-service";
import { OtherShopsRail } from "../../_components/elsewhere/other-shops-rail";

import { BookService } from "./_components/book-service";
import { RequestFreeService } from "./_components/request-free-service";
import { ServiceHowItWorks } from "./_components/service-how-it-works";
import { ServiceJsonLd } from "./_components/service-jsonld";
import { ServicePackages } from "./_components/service-packages";
import { normalisePackages } from "./_components/service-packages-model";
import { SERVICE_SIDEBAR_CTA_ID } from "./_components/service-page-sticky";
import { ServiceProviderCard } from "./_components/service-provider-card";
import { ServiceQuoteCta } from "./_components/service-quote-cta";
import { ServiceReviewsSection } from "./_components/service-reviews-section";
import { ArchetypeLayout } from "./_components/templates/archetype-layout";
import { ServiceRequestPanel } from "./_components/templates/request-panel";
import { ServiceHero } from "./_components/templates/service-hero";
import { asRecord, isBespoke, parseArchetype, parseStaff } from "./_lib/archetypes";
import { buildPanelLabels } from "./_lib/panel-labels";

const ServicePortfolioGallery = dynamic(
  () =>
    import("./_components/service-portfolio-gallery").then((mod) => mod.ServicePortfolioGallery),
  { loading: () => null },
);

const ServicePageSticky = dynamic(
  () => import("./_components/service-page-sticky").then((mod) => mod.ServicePageSticky),
  { loading: () => null },
);

import type { Metadata } from "next";

export const revalidate = 300;

type ServiceDetail = {
  id: string;
  slug: string;
  title: string;
  category: string;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  is_free?: boolean;
  bookable: boolean;
  booking_price_ngwee: number | null;
  portfolio_images: string[];
  includes: string[];
  packages?: unknown;
  archetype?: string;
  attributes?: unknown;
  provider: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    response_time_tier: "fast" | "same_day" | "slow" | null;
  };
};

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

type ServicesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getServicesTranslator(locale: string): Promise<ServicesTranslator> {
  const baseMessages = await getMessages();
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const messages = {
    ...baseMessages,
    services: servicesMessages,
  } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "services",
  }) as unknown as ServicesTranslator;
}

type ServiceReviewsPayload = {
  items: {
    id: string;
    rating: number;
    body: string | null;
    vendor_reply: string | null;
    created_at: string;
  }[];
  rating_avg: number | null;
  rating_count: number;
};

async function fetchServiceReviews(serviceId: string): Promise<ServiceReviewsPayload> {
  const empty: ServiceReviewsPayload = {
    items: [],
    rating_avg: null,
    rating_count: 0,
  };
  try {
    const url = absoluteApiUrl(`/service-reviews?service_id=${encodeURIComponent(serviceId)}`);
    if (!url) {
      return empty;
    }
    const response = await fetch(url, {
      next: { revalidate, tags: [`service:${serviceId}`, "service-reviews"] },
    });
    if (!response.ok) {
      return empty;
    }
    return (await response.json()) as ServiceReviewsPayload;
  } catch {
    return empty;
  }
}

type ResponseTier = NonNullable<ServiceDetail["provider"]["response_time_tier"]>;

function responseTimeLine(
  t: ServicesTranslator,
  tier: ServiceDetail["provider"]["response_time_tier"],
): string | null {
  if (!tier) {
    return null;
  }
  return t(`detail.responseTime.${tier}` as `detail.responseTime.${ResponseTier}`);
}

function badgeVariant(tier: ServiceDetail["provider"]["response_time_tier"]) {
  if (tier === "fast") {
    return "free" as const;
  }
  if (tier === "same_day") {
    return "public" as const;
  }
  return "new" as const;
}

export function generateStaticParams() {
  return [];
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const result = await fetchServiceDetail(slug);
  const t = await getServicesTranslator(locale);

  if (result.kind !== "service") {
    return {
      title: t("browse.title"),
      robots: { index: false, follow: false },
    };
  }

  const service = result.data;
  const description = t("detail.metaDescription", {
    title: service.title,
    area: service.service_area ?? service.provider.display_name,
  });

  return {
    title: t("detail.metaTitle", { title: service.title }),
    description,
    alternates: buildCanonicalAlternates(locale, "s", service.slug),
    // WhatsApp/Twitter rich preview: portfolio photo first, then the
    // generated title + price card.
    ...buildSocialMetadata({
      title: service.title,
      description,
      locale,
      url: buildLocaleCanonical(locale, "s", service.slug),
      imageUrls: [
        ...(service.portfolio_images[0]
          ? [cldUrl(service.portfolio_images[0], { width: 1200 })]
          : []),
        `${buildLocaleCanonical(locale)}/opengraph-image?${new URLSearchParams({
          name: service.title,
          ...(service.from_price_ngwee !== null
            ? { price: formatK(service.from_price_ngwee) }
            : {}),
        }).toString()}`,
      ].filter((url) => url.length > 0),
    }),
    robots: { index: true, follow: true },
  };
}

export default async function ServiceDetailPage({ params }: PageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);

  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const tCatalog = createTranslator({
    locale,
    messages: { catalog: catalogMessages },
    namespace: "catalog",
  }) as ServicesTranslator;
  const [t, result] = await Promise.all([getServicesTranslator(locale), fetchServiceDetail(slug)]);

  if (result.kind === "not_found") notFound();
  if (result.kind === "unavailable") {
    return (
      <ApiUnavailablePanel
        retryHref={`/${locale}/s/${encodeURIComponent(slug)}`}
        labels={{
          title: tCatalog("pdp.unavailableTitle"),
          body: tCatalog("pdp.unavailableBody"),
          retry: tCatalog("pdp.unavailableRetry"),
        }}
        testId="service-unavailable"
      />
    );
  }
  const service = result.data as ServiceDetail;

  const reviewData = await fetchServiceReviews(service.id);
  const tier = service.provider.response_time_tier;
  const quoteLabels = {
    cta: t("detail.requestQuote"),
    dialogTitle: t("detail.requestQuoteDialogTitle"),
    dialogHint: t("detail.requestQuoteDialogHint", {
      vendor: service.provider.display_name,
    }),
    detailsLabel: t("detail.requestQuoteDetailsLabel"),
    detailsPlaceholder: t("detail.requestQuoteDetailsPlaceholder"),
    submit: t("detail.requestQuoteSubmit"),
    submitting: t("detail.requestQuoteSubmitting"),
    cancel: t("detail.requestQuoteCancel"),
    done: t("detail.requestQuoteDone"),
    successTitle: t("detail.requestQuoteSuccessTitle"),
    successBody: t("detail.requestQuoteSuccessBody"),
    successContinued: t("detail.requestQuoteSuccessContinued"),
    signInPrompt: t("detail.requestQuoteSignInPrompt"),
    signInCta: t("detail.requestQuoteSignInCta"),
    errors: {
      empty: t("detail.requestQuoteErrors.empty"),
      tooLong: t("detail.requestQuoteErrors.tooLong"),
      prohibited: t("detail.requestQuoteErrors.prohibited"),
      rateLimited: t("detail.requestQuoteErrors.rateLimited"),
      ownListing: t("detail.requestQuoteErrors.ownListing"),
      generic: t("detail.requestQuoteErrors.generic"),
      signInRequired: t("detail.requestQuoteErrors.signInRequired"),
    },
  };
  const packages = normalisePackages(service.packages);
  const isQuoteBased = service.from_price_ngwee === null;
  const quoteHref = `/${locale}/services/post-job?category=${encodeURIComponent(service.category)}`;
  const archetype = parseArchetype(service.archetype);
  const attrs = asRecord(service.attributes);
  const bespoke = isBespoke(archetype);
  const tt = (key: string, values?: Record<string, string | number>) =>
    t(`templates.${key}`, values);
  const responseLine = responseTimeLine(t, tier);
  const stickyPriceLine = service.is_free
    ? t("detail.free")
    : service.from_price_ngwee !== null
      ? t("detail.fromPrice", { price: formatK(service.from_price_ngwee) })
      : t("detail.askForQuote");
  const stickyKind = service.is_free
    ? ("free" as const)
    : service.bookable && service.booking_price_ngwee
      ? ("book" as const)
      : isQuoteBased || bespoke
        ? ("quote_direct" as const)
        : ("quote_browse" as const);

  return (
    <article className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 pb-28 lg:pb-10">
      <ServiceJsonLd
        service={{
          name: service.title,
          slug: service.slug,
          locale,
          description: service.description,
          serviceArea: service.service_area,
          fromPriceNgwee: service.from_price_ngwee,
          isFree: service.is_free,
          providerName: service.provider.display_name,
          providerSlug: service.provider.slug,
          ratingAvg: reviewData.rating_avg,
          ratingCount: reviewData.rating_count,
        }}
      />
      <Link
        href={`/${locale}/services`}
        className="w-fit text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("browse.title")}
      </Link>

      <ServiceHero
        archetype={archetype}
        archetypeLabel={t(`templates.archetypes.${archetype}`)}
        title={service.title}
        area={service.service_area}
        priceLine={stickyPriceLine}
        responseLine={responseLine}
        images={service.portfolio_images}
        badges={
          <>
            {tier ? (
              <Badge variant={badgeVariant(tier)} label={t(`badges.${tier}` as "badges.fast")} />
            ) : null}
            {service.provider.preferred_badge ? (
              <Badge variant="public" label={t("browse.preferredBadge")} />
            ) : null}
            {service.is_free ? <Badge variant="free" label={t("detail.free")} /> : null}
          </>
        }
      />

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,23rem)] lg:gap-12">
        <div className="flex min-w-0 flex-col gap-8">
          {service.description ? (
            <section className="flex flex-col gap-3" aria-labelledby="service-about-heading">
              <h2 id="service-about-heading" className="font-display text-h2 text-display-ink">
                {t("detail.about")}
              </h2>
              <p className="max-w-3xl text-body leading-relaxed text-text-2">
                {service.description}
              </p>
            </section>
          ) : null}

          {bespoke ? (
            <ArchetypeLayout archetype={archetype} offers={packages} attrs={attrs} t={tt} />
          ) : (
            <ServicePackages
              locale={locale}
              serviceId={service.id}
              vendorName={service.provider.display_name}
              packages={packages}
              t={(key, values) => t(`packages.${key}`, values)}
              quoteLabels={{
                ...quoteLabels,
                errors: {
                  ...quoteLabels.errors,
                  packageUnavailable: t("packages.errors.unavailable"),
                },
              }}
            />
          )}

          {service.includes.length > 0 ? (
            <section className="flex flex-col gap-3" aria-labelledby="service-included-heading">
              <h2 id="service-included-heading" className="font-display text-h2 text-display-ink">
                {t("detail.whatsIncluded")}
              </h2>
              <ul className="grid list-none gap-2 p-0 sm:grid-cols-2">
                {service.includes.map((item) => (
                  <li
                    key={item}
                    className="flex items-start gap-2 rounded-md border border-border bg-surface px-4 py-3 text-sm text-text-2"
                  >
                    <span aria-hidden="true" className="mt-0.5 text-success">
                      {t("detail.includeMarker")}
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {service.portfolio_images.length > 1 ? (
            <ServicePortfolioGallery
              title={service.title}
              publicIds={service.portfolio_images}
              labels={{
                heading: t("detail.portfolio"),
                formatImageAlt: (position) => t("detail.imageAlt", { position }),
                lightbox: {
                  open: t("detail.portfolioLightbox.open"),
                  dialog: t("detail.portfolioLightbox.dialog"),
                  close: t("detail.portfolioLightbox.close"),
                  previous: t("detail.portfolioLightbox.previous"),
                  next: t("detail.portfolioLightbox.next"),
                  zoomIn: t("detail.portfolioLightbox.zoomIn"),
                  zoomOut: t("detail.portfolioLightbox.zoomOut"),
                  indicator: t("detail.portfolioLightbox.indicator"),
                },
              }}
            />
          ) : null}

          <ServiceHowItWorks
            showEscrow={Boolean(service.bookable && service.booking_price_ngwee)}
            labels={{
              heading: t("detail.howItWorks.heading"),
              step1: t("detail.howItWorks.step1"),
              step2: t("detail.howItWorks.step2"),
              step3: t("detail.howItWorks.step3"),
              escrow: t("detail.howItWorks.escrow"),
            }}
          />

          {service.service_area ? (
            <section
              className="rounded-lg border border-border bg-bg-2 p-5"
              aria-labelledby="service-area-heading"
            >
              <h2 id="service-area-heading" className="font-display text-h3 text-display-ink">
                {t("detail.serviceArea")}
              </h2>
              <p className="mt-2 text-sm text-text-2">{service.service_area}</p>
            </section>
          ) : null}

          <ServiceProviderCard
            locale={locale}
            displayName={service.provider.display_name}
            slug={service.provider.slug}
            preferredBadge={service.provider.preferred_badge}
            ratingAvg={reviewData.rating_avg}
            ratingCount={reviewData.rating_count}
            labels={{
              heading: t("detail.providerCard.heading"),
              preferredBadge: t("browse.preferredBadge"),
              reviewCount: t("detail.providerCard.reviewCount", {
                count: reviewData.rating_count,
              }),
              starsAria: t("detail.providerCard.starsAria", {
                rating: "{rating}",
              }),
              viewProfile: t("detail.providerCard.viewProfile"),
            }}
          />

          <ServiceReviewsSection
            reviews={reviewData.items}
            ratingAvg={reviewData.rating_avg}
            ratingCount={reviewData.rating_count}
            labels={{
              heading: t("reviews.heading"),
              subheading: t("reviews.subheading"),
              empty: t("reviews.empty"),
              reviewCountLabel: t("reviews.reviewCount", {
                count: reviewData.rating_count,
              }),
              starsAria: t("reviews.starsAria", { rating: "{rating}" }),
              vendorReply: t("reviews.vendorReply"),
            }}
          />
        </div>

        <aside
          id={SERVICE_SIDEBAR_CTA_ID}
          className="flex flex-col gap-4 lg:sticky lg:top-24 lg:h-fit"
        >
          {service.is_free ? <RequestFreeService locale={locale} serviceId={service.id} /> : null}

          {service.bookable && service.booking_price_ngwee ? (
            <BookService
              locale={locale}
              serviceId={service.id}
              priceNgwee={service.booking_price_ngwee}
            />
          ) : null}

          {bespoke && !service.is_free ? (
            <ServiceRequestPanel
              locale={locale}
              serviceId={service.id}
              vendorName={service.provider.display_name}
              archetype={archetype}
              offers={packages}
              staffNames={parseStaff(attrs).map((member) => member.name)}
              labels={buildPanelLabels(tt, archetype)}
              quoteLabels={quoteLabels}
            />
          ) : (
            <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-2">
              <div className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
                  {t("detail.askForQuote")}
                </p>
                <p className="font-display text-h2 text-display-ink">
                  {service.from_price_ngwee !== null
                    ? t("detail.fromPrice", {
                        price: formatK(service.from_price_ngwee),
                      })
                    : t("detail.askForQuote")}
                </p>
              </div>

              {service.is_free ? null : isQuoteBased ? (
                <ServiceQuoteCta
                  locale={locale}
                  serviceId={service.id}
                  vendorName={service.provider.display_name}
                  hint={t("detail.requestQuoteHintDirect")}
                  labels={quoteLabels}
                />
              ) : (
                <>
                  <LinkButton
                    href={quoteHref}
                    variant="primary"
                    className="w-full rounded-md text-sm font-semibold"
                    LinkComponent={Link}
                  >
                    {t("detail.requestQuote")}
                  </LinkButton>
                  <p className="text-center text-xs text-text-3">{t("detail.requestQuoteHint")}</p>
                </>
              )}
            </section>
          )}
        </aside>
      </div>

      <ServicePageSticky
        locale={locale}
        serviceId={service.id}
        vendorName={service.provider.display_name}
        kind={stickyKind}
        bookingPriceNgwee={service.booking_price_ngwee}
        quoteHref={quoteHref}
        quoteLabels={quoteLabels}
        priceLine={stickyPriceLine}
        labels={{
          ariaLabel: t("detail.stickyCta.ariaLabel"),
          freeCta: t("detail.stickyCta.freeCta"),
          bookCta: t("detail.stickyCta.bookCta"),
          quoteCta: t("detail.stickyCta.quoteCta"),
          freeSubmitting: t("detail.stickyCta.freeSubmitting"),
          bookSubmitting: t("detail.stickyCta.bookSubmitting"),
          errors: {
            authRequired: quoteLabels.errors.signInRequired,
            generic: quoteLabels.errors.generic,
          },
        }}
      />

      {/* Founder rule: related items from OTHER shops, not only this one. */}
      {service.provider.slug ? (
        <Suspense fallback={null}>
          <OtherShopsRail
            locale={locale}
            vendorSlug={service.provider.slug}
            lead="service"
            focusServiceId={service.id}
            excludeIds={[service.id]}
          />
        </Suspense>
      ) : null}
    </article>
  );
}
