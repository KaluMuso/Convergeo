import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BetaGate } from "./_components/beta-gate";

import type { Metadata } from "next";

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

async function loadMarketing(locale: string): Promise<AbstractIntlMessages> {
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  return { marketing: marketingMessages } as AbstractIntlMessages;
}

async function getMarketingTranslator(locale: string): Promise<MarketingTranslator> {
  const baseMessages = await getMessages();
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  const messages = { ...baseMessages, marketing: marketingMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "marketing.beta",
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
    alternates: { canonical: `/${locale}/beta` },
    // Pre-launch invite gate: keep it out of the index.
    robots: { index: false, follow: false },
  };
}

export default async function BetaPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getMarketingTranslator(locale);
  const clientMessages = await loadMarketing(locale);

  return (
    <main id="marketing-main" className="mx-auto w-full max-w-md px-4 py-10">
      <header className="mb-8 space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          {t("hero.eyebrow")}
        </p>
        <h1 className="font-display text-h1 text-display-ink">{t("hero.headline")}</h1>
        <p className="text-body text-text-2">{t("hero.subhead")}</p>
      </header>

      <NextIntlClientProvider locale={locale} messages={clientMessages}>
        <BetaGate locale={locale} />
      </NextIntlClientProvider>
    </main>
  );
}
