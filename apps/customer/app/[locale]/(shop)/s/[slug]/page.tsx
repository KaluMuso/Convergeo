import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

import { BookService } from "./_components/book-service";
import { ServiceQuoteCta } from "./_components/service-quote-cta";
import { ServiceReviewsSection } from "./_components/service-reviews-section";

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
  bookable: boolean;
  booking_price_ngwee: number | null;
  portfolio_images: string[];
  includes: string[];
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
  const messages = { ...baseMessages, services: servicesMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "services",
  }) as unknown as ServicesTranslator;
}

async function fetchService(slug: string): Promise<ServiceDetail | null> {
  try {
    const url = absoluteApiUrl(`/services/${encodeURIComponent(slug)}`);
    if (!url) {
      return null;
    }
    const response = await fetch(url, {
      next: { revalidate, tags: [`service:${slug}`, "services"] },
    });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ServiceDetail;
  } catch {
    return null;
  }
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
  const empty: ServiceReviewsPayload = { items: [], rating_avg: null, rating_count: 0 };
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
  return LOCALES.map((locale) => ({ locale, slug: "placeholder" }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const service = await fetchService(slug);
  const t = await getServicesTranslator(locale);

  if (!service) {
    return { title: t("browse.title"), robots: { index: false, follow: false } };
  }

  const description = t("detail.metaDescription", {
    title: service.title,
    area: service.service_area ?? service.provider.display_name,
  });

  return {
    title: t("detail.metaTitle", { title: service.title }),
    description,
    alternates: buildCanonicalAlternates(locale, "s", service.slug),
    openGraph: {
      title: service.title,
      description,
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "s", service.slug),
    },
    robots: { index: true, follow: true },
  };
}

export default async function ServiceDetailPage({ params }: PageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);

  const t = await getServicesTranslator(locale);
  const service = await fetchService(slug);

  if (!service) {
    notFound();
  }

  const reviewData = await fetchServiceReviews(service.id);
  const tier = service.provider.response_time_tier;
  const isQuoteBased = service.from_price_ngwee === null;
  const quoteHref = `/${locale}/services/post-job?category=${encodeURIComponent(service.category)}`;
  const heroImage = service.portfolio_images[0];

  return (
    <article className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 pb-10">
      <Link
        href={`/${locale}/services`}
        className="w-fit text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("browse.title")}
      </Link>

      <header className="overflow-hidden rounded-lg border border-border bg-primary-tint shadow-2">
        <div className="grid min-h-[22rem] lg:grid-cols-[minmax(0,1fr)_minmax(24rem,0.9fr)]">
          <div className="flex flex-col justify-center gap-5 p-6 md:p-10 lg:p-12">
            <div className="flex flex-wrap items-center gap-2">
              {tier ? (
                <Badge variant={badgeVariant(tier)} label={t(`badges.${tier}` as "badges.fast")} />
              ) : null}
              {service.provider.preferred_badge ? (
                <Badge variant="public" label={t("browse.preferredBadge")} />
              ) : null}
            </div>
            <div className="space-y-3">
              <h1 className="font-display text-hero text-display-ink">{service.title}</h1>
              {service.service_area ? (
                <p className="text-sm text-text-2">{service.service_area}</p>
              ) : null}
              <p className="text-lg font-semibold text-text">
                {service.from_price_ngwee !== null
                  ? t("detail.fromPrice", { price: formatK(service.from_price_ngwee) })
                  : t("detail.askForQuote")}
              </p>
            </div>
          </div>

          {heroImage ? (
            <CloudinaryImageStatic
              publicId={heroImage}
              alt={service.title}
              width={960}
              sizes="(max-width: 1024px) 100vw, 45vw"
              ratio="4/3"
              priority
              className="h-full rounded-none"
            />
          ) : (
            <div
              className="min-h-64 bg-gradient-to-br from-primary/15 via-surface to-primary/5"
              aria-hidden="true"
            />
          )}
        </div>
      </header>

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
            <section className="flex flex-col gap-4" aria-labelledby="service-portfolio-heading">
              <h2 id="service-portfolio-heading" className="font-display text-h2 text-display-ink">
                {t("detail.portfolio")}
              </h2>
              <ul className="grid list-none grid-cols-2 gap-3 p-0 md:grid-cols-3">
                {service.portfolio_images.slice(1).map((publicId, index) => (
                  <li key={publicId} className="overflow-hidden rounded-lg border border-border">
                    <CloudinaryImageStatic
                      publicId={publicId}
                      alt={t("detail.imageAlt", { position: index + 2 })}
                      width={480}
                      sizes="(max-width: 640px) 50vw, 33vw"
                      ratio="4/3"
                    />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

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

          <ServiceReviewsSection
            reviews={reviewData.items}
            ratingAvg={reviewData.rating_avg}
            ratingCount={reviewData.rating_count}
            labels={{
              heading: t("reviews.heading"),
              subheading: t("reviews.subheading"),
              empty: t("reviews.empty"),
              reviewCountLabel: t("reviews.reviewCount", { count: reviewData.rating_count }),
              starsAria: t("reviews.starsAria", { rating: "{rating}" }),
              vendorReply: t("reviews.vendorReply"),
            }}
          />
        </div>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:h-fit">
          {service.bookable && service.booking_price_ngwee ? (
            <BookService
              locale={locale}
              serviceId={service.id}
              priceNgwee={service.booking_price_ngwee}
            />
          ) : null}

          <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-2">
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
                {t("detail.askForQuote")}
              </p>
              <p className="font-display text-h2 text-display-ink">
                {service.from_price_ngwee !== null
                  ? t("detail.fromPrice", { price: formatK(service.from_price_ngwee) })
                  : t("detail.askForQuote")}
              </p>
            </div>

            {isQuoteBased ? (
              <ServiceQuoteCta
                locale={locale}
                serviceId={service.id}
                vendorName={service.provider.display_name}
                hint={t("detail.requestQuoteHintDirect")}
                labels={{
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
                }}
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

            <div className="border-t border-border pt-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
                {t("detail.provider")}
              </p>
              <p className="mt-1 font-semibold text-text">{service.provider.display_name}</p>
              {service.provider.slug ? (
                <Link
                  href={`/${locale}/v/${service.provider.slug}`}
                  className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {t("detail.providerCta")}
                </Link>
              ) : null}
            </div>
          </section>
        </aside>
      </div>
    </article>
  );
}
