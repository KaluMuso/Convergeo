"use client";

import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useParams } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

import enMarketing from "../../../../packages/i18n/messages/en/marketing.json";

type ErrorProps = {
  reset: () => void;
};

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

export default function ErrorBoundary({ reset }: ErrorProps) {
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "en";

  // The root client provider only carries common + legal, so resolve the marketing
  // namespace directly from the EN messages (the only locale shipped today).
  const t = createTranslator({
    locale,
    messages: { marketing: enMarketing } as AbstractIntlMessages,
    namespace: "marketing.error",
  }) as unknown as MarketingTranslator;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-6">
      <p aria-hidden="true" className="font-mono text-5xl font-bold text-primary">
        {t("code")}
      </p>
      <h1 className="font-display text-h1 text-display-ink">{t("heading")}</h1>
      <p className="text-body text-text-2">{t("body")}</p>
      <div className="mt-2 flex w-full flex-col gap-3">
        <button
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
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
