"use client";

import { useTranslations } from "next-intl";

/**
 * M17-P04 — skeleton, empty and error states.
 *
 * The skeleton is deliberately poster-shaped and CSS-only: a loading state that
 * pulls its own assets would spend data before the feed has shown anything.
 */
export function FeedSkeleton() {
  const t = useTranslations("clips");
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="clips-skeleton"
      className="flex h-[100dvh] w-full flex-col gap-3 p-4"
    >
      <span className="sr-only">{t("feed.loading")}</span>
      <div aria-hidden className="h-2/3 w-full animate-pulse rounded-2 bg-bg-2" />
      <div aria-hidden className="h-4 w-2/3 animate-pulse rounded-1 bg-bg-2" />
      <div aria-hidden className="h-4 w-1/3 animate-pulse rounded-1 bg-bg-2" />
    </div>
  );
}

export function FeedEmpty() {
  const t = useTranslations("clips");
  return (
    <div data-testid="clips-empty" className="mx-auto max-w-md px-4 py-16 text-center">
      <h2 className="text-h3 font-semibold text-text">{t("feed.empty.title")}</h2>
      <p className="mt-2 text-sm text-muted">{t("feed.empty.body")}</p>
    </div>
  );
}

export function FeedError({ onRetry }: { onRetry?: () => void }) {
  const t = useTranslations("clips");
  return (
    <div role="alert" data-testid="clips-error" className="mx-auto max-w-md px-4 py-16 text-center">
      <h2 className="text-h3 font-semibold text-text">{t("feed.error.title")}</h2>
      <p className="mt-2 text-sm text-muted">{t("feed.error.body")}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="tap mt-4 min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("feed.error.retry")}
        </button>
      ) : null}
    </div>
  );
}
