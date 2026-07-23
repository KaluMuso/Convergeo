"use client";

import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

/**
 * Branded offline fallback — M16-P02. Precached and served by the service
 * worker when a navigation fails with no network. Messaging is HONEST: it
 * tells the shopper that previously viewed pages still work and never implies
 * an action succeeded offline. Client component so the retry button can reload
 * once connectivity returns; strings come from the `common` namespace already
 * provided by the locale layout.
 */
export default function OfflinePage() {
  const t = useTranslations("common.offline");
  const locale = useLocale();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-6">
      <p
        aria-hidden="true"
        className="font-mono text-sm font-bold uppercase tracking-wide text-text-3"
      >
        {t("code")}
      </p>
      <h1 className="font-display text-h1 text-display-ink">{t("heading")}</h1>
      <p className="text-body text-text-2">{t("body")}</p>
      <div className="mt-2 flex w-full flex-col gap-3">
        <button
          type="button"
          onClick={() => {
            window.location.reload();
          }}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
        >
          {t("retry")}
        </button>
        <LinkButton href={`/${locale}`} variant="secondary" LinkComponent={Link}>
          {t("home")}
        </LinkButton>
      </div>
    </main>
  );
}
