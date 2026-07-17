import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BookService } from "./_components/book-service";
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

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

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
    const response = await fetch(`${getApiBaseUrl()}/services/${encodeURIComponent(slug)}`, {
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
    const response = await fetch(
      `${getApiBaseUrl()}/service-reviews?service_id=${encodeURIComponent(serviceId)}`,
      { next: { revalidate, tags: [`service:${serviceId}`, "service-reviews"] } },
    );
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
  const quoteHref = `/${locale}/services/post-job?category=${encodeURIComponent(service.category)}`;

  return (
    <article className="flex flex-col gap-6 pb-8 lg:mx-auto lg:w-full lg:max-w-5xl">
      {/* Themed overlay hero — dark aubergine gradient (no per-category theme data yet). */}
      <header className="relative overflow-hidden rounded-lg">
        {service.portfolio_images[0] ? (
          <CloudinaryImage
            publicId={service.portfolio_images[0]}
            alt={service.title}
            width={1280}
            ratio="16/9"
            priority
            className="h-full w-full object-cover"
          />
        ) : (
          <div
            className="aspect-[16/9] w-full bg-gradient-to-br from-panel to-panel-2"
            aria-hidden
          />
        )}
        <div
          className="absolute inset-0 bg-gradient-to-t from-panel via-panel/40 to-transparent"
          aria-hidden
        />
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-2 p-4 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            {tier ? (
              <Badge variant={badgeVariant(tier)} label={t(`badges.${tier}` as "badges.fast")} />
            ) : null}
            {service.provider.preferred_badge ? (
              <Badge variant="public" label={t("browse.preferredBadge")} />
            ) : null}
          </div>
          <h1 className="font-display text-h1 text-panel-text">{service.title}</h1>
          {service.service_area ? (
            <p className="text-sm text-panel-muted">{service.service_area}</p>
          ) : null}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex flex-col gap-6">
          {service.description ? (
            <section className="flex flex-col gap-2">
              <h2 className="font-display text-h3 text-display-ink">{t("detail.about")}</h2>
              <p className="text-sm leading-relaxed text-text-2">{service.description}</p>
            </section>
          ) : null}

          {service.includes.length > 0 ? (
            <section className="flex flex-col gap-2">
              <h2 className="font-display text-h3 text-display-ink">{t("detail.whatsIncluded")}</h2>
              <ul className="flex list-none flex-col gap-2 p-0">
                {service.includes.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm text-text-2">
                    <span aria-hidden className="mt-0.5 text-success">
                      {t("detail.includeMarker")}
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {service.portfolio_images.length > 1 ? (
            <section className="flex flex-col gap-3">
              <h2 className="font-display text-h3 text-display-ink">{t("detail.portfolio")}</h2>
              <ul className="grid list-none grid-cols-2 gap-2 p-0">
                {service.portfolio_images.slice(1).map((publicId, index) => (
                  <li key={publicId} className="overflow-hidden rounded-lg border border-border">
                    <CloudinaryImage
                      publicId={publicId}
                      alt={t("detail.imageAlt", { position: index + 2 })}
                      width={480}
                      ratio="4/3"
                    />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {service.service_area ? (
            <section className="flex flex-col gap-2">
              <h2 className="font-display text-h3 text-display-ink">{t("detail.serviceArea")}</h2>
              <p className="text-sm text-text-2">{service.service_area}</p>
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

        {/* Sticky sidebar — direct booking (when bookable) alongside the RFQ handoff. */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:h-fit">
          {service.bookable && service.booking_price_ngwee ? (
            <BookService
              locale={locale}
              serviceId={service.id}
              priceNgwee={service.booking_price_ngwee}
            />
          ) : null}
          <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 shadow-1">
            <p className="text-lg font-semibold text-text">
              {service.from_price_ngwee
                ? t("detail.fromPrice", { price: formatK(service.from_price_ngwee) })
                : t("detail.askForQuote")}
            </p>
            <Link
              href={quoteHref}
              className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-surface transition-colors hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {t("detail.requestQuote")}
            </Link>
            <p className="text-center text-xs text-text-3">{t("detail.requestQuoteHint")}</p>
            <div className="border-t border-border pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-3">
                {t("detail.provider")}
              </p>
              <p className="mt-1 font-semibold text-text">{service.provider.display_name}</p>
              {service.provider.slug ? (
                <Link
                  href={`/${locale}/v/${service.provider.slug}`}
                  className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-primary"
                >
                  {t("detail.providerCta")}
                </Link>
              ) : null}
            </div>
          </div>
        </aside>
      </div>
    </article>
  );
}
