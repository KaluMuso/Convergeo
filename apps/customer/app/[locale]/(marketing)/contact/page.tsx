import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { buildWhatsappLink } from "./_components/config";
import { ContactForm, type ContactFormLabels } from "./_components/contact-form";

import type { Metadata } from "next";

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

async function getMarketingTranslator(locale: string): Promise<MarketingTranslator> {
  const baseMessages = await getMessages();
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  const messages = { ...baseMessages, marketing: marketingMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "marketing.contact",
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
    alternates: { canonical: `/${locale}/contact` },
  };
}

function buildLabels(t: MarketingTranslator): ContactFormLabels {
  return {
    nameLabel: t("form.nameLabel"),
    namePlaceholder: t("form.namePlaceholder"),
    contactLabel: t("form.phoneLabel"),
    contactPlaceholder: t("form.phonePlaceholder"),
    messageLabel: t("form.messageLabel"),
    messagePlaceholder: t("form.messagePlaceholder"),
    requiredMarker: t("form.requiredMarker"),
    submit: t("form.submit"),
    submitting: t("form.submitting"),
    success: t("form.success"),
    errorGeneric: t("form.errorGeneric"),
    errorRateLimited: t("form.errorRateLimited"),
    validation: {
      nameRequired: t("form.validation.nameRequired"),
      nameTooLong: t("form.validation.nameTooLong"),
      messageRequired: t("form.validation.messageRequired"),
      messageTooShort: t("form.validation.messageTooShort"),
      messageTooLong: t("form.validation.messageTooLong"),
      contactTooLong: t("form.validation.contactTooLong"),
    },
  };
}

export default async function ContactPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getMarketingTranslator(locale);
  const whatsappHref = buildWhatsappLink();

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <header className="mb-8 space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          {t("hero.eyebrow")}
        </p>
        <h1 className="font-display text-h1 text-display-ink">{t("hero.headline")}</h1>
        <p className="text-body text-text-2">{t("hero.subhead")}</p>
      </header>

      <section className="mb-8 space-y-3 rounded-lg border border-border bg-bg-2 p-6">
        <h2 className="font-display text-h2 text-display-ink">{t("whatsapp.heading")}</h2>
        <p className="text-body text-text">{t("whatsapp.body")}</p>
        <a
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-body font-medium text-surface"
          href={whatsappHref}
          rel="noopener noreferrer"
          target="_blank"
        >
          {t("whatsapp.cta")}
        </a>
        <p className="text-sm text-text-2">{t("whatsapp.hint")}</p>
      </section>

      <section className="mb-8 space-y-2">
        <h2 className="font-display text-h3 text-display-ink">{t("hours.heading")}</h2>
        <p className="text-body text-text-2">{t("hours.body")}</p>
      </section>

      <section className="space-y-4">
        <h2 className="font-display text-h2 text-display-ink">{t("form.heading")}</h2>
        <ContactForm labels={buildLabels(t)} />
      </section>
    </main>
  );
}
