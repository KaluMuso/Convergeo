import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

async function getMarketingTranslator(locale: string): Promise<MarketingTranslator> {
  const baseMessages = await getMessages();
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  const messages = { ...baseMessages, marketing: marketingMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "marketing.about",
  }) as unknown as MarketingTranslator;
}

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getMarketingTranslator(locale);
  return {
    title: t("meta.title"),
    description: t("meta.description"),
    alternates: { canonical: `/${locale}/about` },
    openGraph: {
      title: t("meta.title"),
      description: t("meta.description"),
      type: "website",
      locale,
      url: `/${locale}/about`,
    },
  };
}

const VALUE_KEYS = ["trust", "local", "fast", "fair"] as const;
const STEP_KEYS = ["step1", "step2", "step3", "step4"] as const;

export default async function AboutPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getMarketingTranslator(locale);

  return (
    <main id="marketing-main" className="mx-auto w-full max-w-2xl px-4 py-8">
      <header className="mb-10 space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          {t("hero.eyebrow")}
        </p>
        <h1 className="font-display text-h1 text-display-ink">{t("hero.headline")}</h1>
        <p className="text-body text-text-2">{t("hero.subhead")}</p>
      </header>

      <section className="mb-10 space-y-3">
        <h2 className="font-display text-h2 text-display-ink">{t("mission.heading")}</h2>
        <p className="text-body leading-relaxed text-text">{t("mission.body")}</p>
      </section>

      <section className="mb-10 space-y-4">
        <h2 className="font-display text-h2 text-display-ink">{t("values.heading")}</h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {VALUE_KEYS.map((key) => (
            <li key={key} className="rounded-lg border border-border bg-bg-2 p-4">
              <h3 className="mb-1 font-body text-lg font-semibold text-text">
                {t(`values.${key}.title`)}
              </h3>
              <p className="text-sm text-text-2">{t(`values.${key}.body`)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mb-10 space-y-4">
        <h2 className="font-display text-h2 text-display-ink">{t("howItWorks.heading")}</h2>
        <ol className="space-y-3">
          {STEP_KEYS.map((key, index) => (
            <li key={key} className="flex gap-3">
              <span
                aria-hidden="true"
                className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-primary font-mono text-sm text-surface"
              >
                {index + 1}
              </span>
              <p className="pt-1 text-body text-text">{t(`howItWorks.${key}`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-4 rounded-lg border border-border bg-bg-2 p-6">
        <h2 className="font-display text-h2 text-display-ink">{t("cta.heading")}</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
            href={`/${locale}`}
          >
            {t("cta.browse")}
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-body font-medium text-text"
            href={`/${locale}/sell`}
          >
            {t("cta.sell")}
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-body font-medium text-text"
            href={`/${locale}/help`}
          >
            {t("cta.help")}
          </Link>
        </div>
      </section>
    </main>
  );
}
