"use client";

import { useTranslations } from "next-intl";

const TIP_KEYS = ["photos", "title", "price", "stock"] as const;
const STATUS_KEYS = ["draft", "active", "paused"] as const;

/**
 * Collapsible "how to make a listing that sells" panel. Native <details> so it
 * works before hydration and costs no JS on 3G.
 */
export function ListingTipsPanel({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const t = useTranslations("vendor");
  return (
    <details
      className="group rounded-xl border border-border bg-surface p-3"
      open={defaultOpen}
      data-testid="vendor-listing-tips"
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-text">
        <span>{t("listings.guide.heading")}</span>
        <span aria-hidden="true" className="text-text-3 transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <dl className="mt-2 flex flex-col gap-3">
        {TIP_KEYS.map((key) => (
          <div key={key}>
            <dt className="text-sm font-medium text-text">{t(`listings.guide.${key}.title`)}</dt>
            <dd className="mt-0.5 text-sm text-text-2">{t(`listings.guide.${key}.body`)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/** What Draft / Live / Paused mean — shown once above the listings list. */
export function ListingStatusGuide() {
  const t = useTranslations("vendor");
  return (
    <details
      className="group rounded-xl border border-border bg-bg-2 p-3"
      data-testid="vendor-listing-status-guide"
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-text">
        <span>{t("listings.manage.statusGuide.heading")}</span>
        <span aria-hidden="true" className="text-text-3 transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <dl className="mt-2 flex flex-col gap-2">
        {STATUS_KEYS.map((key) => (
          <div key={key}>
            <dt className="text-sm font-medium text-text">{t(`listings.manage.status.${key}`)}</dt>
            <dd className="text-sm text-text-2">{t(`listings.manage.statusGuide.${key}`)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-text-2">{t("listings.manage.statusGuide.kycNote")}</p>
    </details>
  );
}

/** One line under a listing card: who can see it right now. */
export function ListingVisibilityHint({ status }: { status: string }) {
  const t = useTranslations("vendor");
  if (status !== "draft" && status !== "active" && status !== "paused") {
    return null;
  }
  return <p className="text-xs text-text-2">{t(`listings.manage.statusHint.${status}`)}</p>;
}
