import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { buildWhatsappLink } from "../contact/_components/config";

import { HelpSearch } from "./_components/help-search";
import { buildSearchIndex } from "./_lib/content";

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
    namespace: "marketing.help",
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
    alternates: { canonical: `/${locale}/help` },
  };
}

export default async function HelpPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getMarketingTranslator(locale);
  const index = buildSearchIndex();
  const clientMessages = await loadMarketing(locale);

  return (
    <main id="marketing-main" className="mx-auto w-full max-w-2xl px-4 py-8">
      <header className="mb-8 space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          {t("hero.eyebrow")}
        </p>
        <h1 className="font-display text-h1 text-display-ink">{t("hero.headline")}</h1>
        <p className="text-body text-text-2">{t("hero.subhead")}</p>
      </header>

      <NextIntlClientProvider locale={locale} messages={clientMessages}>
        <HelpSearch index={index} locale={locale} />
      </NextIntlClientProvider>

      <section className="mt-12 space-y-3 rounded-lg border border-border bg-bg-2 p-6">
        <h2 className="font-display text-h2 text-display-ink">{t("cta.heading")}</h2>
        <p className="text-body text-text-2">{t("cta.body")}</p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <a
            className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
            href={buildWhatsappLink()}
            rel="noopener noreferrer"
            target="_blank"
          >
            {t("cta.whatsapp")}
          </a>
          <LinkButton href={`/${locale}/contact`} variant="secondary" LinkComponent={Link}>
            {t("cta.contact")}
          </LinkButton>
        </div>
      </section>
    </main>
  );
}
