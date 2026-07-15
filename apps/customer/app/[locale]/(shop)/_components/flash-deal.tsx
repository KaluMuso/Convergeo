import { Countdown } from "@vergeo/ui/src/countdown";
import Link from "next/link";

import type { MerchSlotRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type FlashDealProps = {
  slot?: MerchSlotRow;
  locale: string;
  t: CatalogTranslator;
};

function readString(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * Admin-configurable flash-deal banner with a live countdown. Renders only when
 * the slot has a valid end instant that is still in the future — an expired deal
 * (checked server-side) drops out rather than showing a dead banner. The end
 * instant comes from the payload's `ends_at`, falling back to the slot's
 * `schedule_to`. Headline/tag/CTA are admin content (payload strings) with
 * localised defaults.
 */
export function FlashDeal({ slot, locale, t }: FlashDealProps) {
  if (!slot) {
    return null;
  }

  const payload = slot.payload;
  const endsAt = readString(payload, "ends_at") ?? slot.schedule_to ?? undefined;
  if (!endsAt) {
    return null;
  }
  const endsAtMs = new Date(endsAt).getTime();
  if (Number.isNaN(endsAtMs) || endsAtMs <= Date.now()) {
    return null;
  }

  const tag = readString(payload, "tag") ?? t("home.flash.defaultTag");
  const headline = readString(payload, "headline") ?? t("home.flash.defaultHeadline");
  const ctaLabel = readString(payload, "cta_label") ?? t("home.flash.defaultCta");
  const ctaHref = readString(payload, "cta_href") ?? `/${locale}/search`;

  return (
    <section
      aria-labelledby="home-flash-heading"
      className="motion-rise flex flex-col gap-4 overflow-hidden rounded-lg bg-panel p-6 text-panel-text shadow-2 lg:flex-row lg:items-center lg:justify-between lg:gap-8 lg:p-8"
    >
      <div className="flex flex-col gap-2">
        <p className="text-micro font-semibold uppercase tracking-wide text-accent">{tag}</p>
        <h2 id="home-flash-heading" className="font-display text-h2 text-panel-text">
          {headline}
        </h2>
      </div>
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center lg:shrink-0">
        <Countdown
          endsAt={endsAt}
          labels={{
            days: t("home.flash.days"),
            hours: t("home.flash.hours"),
            minutes: t("home.flash.minutes"),
            seconds: t("home.flash.seconds"),
            expired: t("home.flash.expired"),
            ariaLabel: (time) => t("home.flash.ariaLabel", { time }),
          }}
          className="flex items-center gap-3"
        />
        <Link
          href={ctaHref}
          className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-pill bg-panel-text px-6 text-sm font-semibold text-panel transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {ctaLabel}
        </Link>
      </div>
    </section>
  );
}
