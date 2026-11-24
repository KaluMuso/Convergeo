import { formatK } from "@vergeo/i18n";

import { RequestQuoteButton } from "../../../_components/pdp/request-quote-button";

import { buildPrefill, type ServicePackage } from "./service-packages-model";

import type { RequestQuoteLabels } from "../../../_components/pdp/request-quote-button";

type Translate = (key: string, values?: Record<string, string | number>) => string;

type ServicePackagesProps = {
  locale: string;
  serviceId: string;
  vendorName: string;
  packages: ServicePackage[];
  /** `services.packages` translator. */
  t: Translate;
  /** Shared request-quote modal labels (from `services.detail`). */
  quoteLabels: RequestQuoteLabels;
};

/**
 * Package comparison — server-rendered; the only client JS is the existing
 * request-quote modal per card. 360px-first: one card per tier in a horizontal
 * snap row (swipe to compare); three columns from `sm`.
 *
 * Choosing a package never takes payment (SP-1): it opens the quote request,
 * prefilled with the package and carrying its id so the vendor quotes against it.
 */
export function ServicePackages({
  locale,
  serviceId,
  vendorName,
  packages,
  t,
  quoteLabels,
}: ServicePackagesProps) {
  if (packages.length === 0) {
    return null;
  }

  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="service-packages-heading"
      data-testid="service-packages"
    >
      <div className="space-y-1">
        <h2 id="service-packages-heading" className="font-display text-h2 text-display-ink">
          {t("heading")}
        </h2>
        <p className="text-sm text-text-2">{t("subheading", { vendor: vendorName })}</p>
        {packages.length > 1 ? (
          <p className="text-xs text-text-3 sm:hidden">{t("compareHint")}</p>
        ) : null}
      </div>

      <ul
        className="-mx-4 flex snap-x snap-mandatory list-none gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0"
        aria-label={t("heading")}
      >
        {packages.map((pkg) => (
          <li
            key={pkg.id}
            className="flex shrink-0 basis-4/5 snap-start flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-1 sm:basis-auto"
            data-testid={`service-package-${pkg.tier}`}
          >
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3">
                {t(`tier.${pkg.tier}`)}
              </p>
              <h3 className="font-semibold text-text">{pkg.name}</h3>
              <p
                className="font-display text-h3 text-display-ink"
                data-testid="service-package-price"
              >
                {pkg.price_ngwee !== null ? formatK(pkg.price_ngwee) : t("priceQuote")}
              </p>
            </div>

            {pkg.description ? <p className="text-sm text-text-2">{pkg.description}</p> : null}

            <dl className="grid grid-cols-1 gap-1 text-sm text-text-2">
              <div className="flex gap-2">
                <dt className="sr-only">{t("deliveryLabel")}</dt>
                <dd>{t("delivery", { days: pkg.delivery_days })}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="sr-only">{t("revisionsLabel")}</dt>
                <dd>
                  {pkg.revisions === null
                    ? t("revisionsNA")
                    : t("revisions", { count: pkg.revisions })}
                </dd>
              </div>
            </dl>

            {pkg.includes.length > 0 ? (
              <ul className="flex list-none flex-col gap-1 p-0 text-sm text-text-2">
                {pkg.includes.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span aria-hidden="true" className="text-success">
                      {t("includeMarker")}
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="mt-auto">
              <RequestQuoteButton
                locale={locale}
                serviceId={serviceId}
                packageId={pkg.id}
                vendorName={vendorName}
                initialDetails={buildPrefill(pkg, t, formatK)}
                ctaTestId={`service-package-cta-${pkg.tier}`}
                variant={pkg.tier === "standard" ? "primary" : "secondary"}
                className="w-full rounded-md text-sm font-semibold"
                labels={{
                  ...quoteLabels,
                  cta: t("cta"),
                  dialogTitle: t("dialogTitle", { name: pkg.name }),
                }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-3">{t("noPaymentNote")}</p>
    </section>
  );
}
