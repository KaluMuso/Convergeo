import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { CommissionTable } from "./_components/commission-table";
import { Cta } from "./_components/cta";
import { Faq, FAQ_KEYS } from "./_components/faq";
import { Hero } from "./_components/hero";
import { HowItWorks } from "./_components/how-it-works";
import { KycExplainer } from "./_components/kyc-explainer";
import { PayoutPromise } from "./_components/payout-promise";

import type { Metadata } from "next";

type PitchTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getPitchTranslator(locale: string): Promise<PitchTranslator> {
  const baseMessages = await getMessages();
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const messages = { ...baseMessages, vendor: vendorMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "vendor.pitch",
  }) as unknown as PitchTranslator;
}

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getPitchTranslator(locale);

  return {
    title: t("meta.title"),
    description: t("meta.description"),
    alternates: {
      canonical: `/${locale}/sell`,
    },
    openGraph: {
      title: t("meta.title"),
      description: t("meta.description"),
      type: "website",
      locale,
      url: `/${locale}/sell`,
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

function buildFaqSchema(t: PitchTranslator) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ_KEYS.map((key) => ({
      "@type": "Question",
      name: t(`faq.items.${key}.question`),
      acceptedAnswer: {
        "@type": "Answer",
        text: t(`faq.items.${key}.answer`),
      },
    })),
  };
}

export default async function SellPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getPitchTranslator(locale);
  const faqSchema = buildFaqSchema(t);

  return (
    <>
      <script
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
        type="application/ld+json"
      />
      <main id="marketing-main">
        <Hero locale={locale} t={t} />
        <CommissionTable t={t} />
        <HowItWorks t={t} />
        <KycExplainer t={t} />
        <PayoutPromise t={t} />
        <Faq t={t} />
        <Cta locale={locale} t={t} />
      </main>
    </>
  );
}
