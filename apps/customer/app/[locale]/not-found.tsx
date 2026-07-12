import { loadNamespace, DEFAULT_LOCALE, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getLocale } from "next-intl/server";

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

async function getMarketingTranslator(locale: string): Promise<MarketingTranslator> {
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  const messages = { marketing: marketingMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "marketing.notFound",
  }) as unknown as MarketingTranslator;
}

export default async function NotFound() {
  let locale: string = DEFAULT_LOCALE;
  try {
    locale = await getLocale();
  } catch {
    locale = DEFAULT_LOCALE;
  }
  const t = await getMarketingTranslator(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-6">
      <p aria-hidden="true" className="font-mono text-5xl font-bold text-primary">
        {t("code")}
      </p>
      <h1 className="font-display text-h1 text-display-ink">{t("heading")}</h1>
      <p className="text-body text-text-2">{t("body")}</p>
      <div className="mt-2 flex w-full flex-col gap-3">
        <Link
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
          href={`/${locale}`}
        >
          {t("home")}
        </Link>
        <Link
          className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-body font-medium text-text"
          href={`/${locale}/search`}
        >
          {t("search")}
        </Link>
        <Link
          className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-body font-medium text-text"
          href={`/${locale}/help`}
        >
          {t("help")}
        </Link>
      </div>
    </main>
  );
}
