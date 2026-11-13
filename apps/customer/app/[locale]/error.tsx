"use client";

import { useReportClientError } from "@vergeo/observability";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useParams } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

import { getApiBaseUrl } from "../../lib/api-base-url";
import { resolveMarketingErrorCopy } from "../../lib/marketing-error-copy";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

export default function ErrorBoundary({ error, reset }: ErrorProps) {
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "en";
  const marketingError = resolveMarketingErrorCopy(locale);

  useReportClientError(
    error,
    {
      boundary: "route",
      application: "customer",
    },
    {
      apiBaseUrl: getApiBaseUrl(),
      locale,
    },
  );

  const t = createTranslator({
    locale,
    messages: { marketing: { error: marketingError } } as AbstractIntlMessages,
    namespace: "marketing.error",
  }) as unknown as MarketingTranslator;

  return (
    <main className="mx-auto flex min-h-[70dvh] w-full max-w-xl flex-col items-start justify-center gap-4 px-4 py-16 sm:px-6">
      <p
        aria-hidden="true"
        className="m-0 font-display text-[clamp(4.5rem,18vw,8rem)] font-extrabold leading-none tracking-tight text-accent"
      >
        {t("code")}
      </p>
      <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{t("heading")}</h1>
      <p className="m-0 max-w-prose text-body text-text-2">{t("body")}</p>
      <div className="mt-2 flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-body font-semibold text-[var(--primary-btn-fg)] hover:bg-[var(--primary-btn-hover)]"
          onClick={reset}
          type="button"
        >
          {t("retry")}
        </button>
        <LinkButton href={`/${locale}`} variant="secondary" LinkComponent={Link}>
          {t("home")}
        </LinkButton>
        <LinkButton href={`/${locale}/help`} variant="secondary" LinkComponent={Link}>
          {t("help")}
        </LinkButton>
      </div>
    </main>
  );
}
