import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getLegalTranslator, LegalShell } from "../_components/legal-shell";

import type { Metadata } from "next";

const SECTION_IDS = [
  "introduction",
  "marketplace",
  "escrow",
  "pricing",
  "orders",
  "tax",
  "prohibited",
  "liability",
  "changes",
  "contact",
] as const;

const UPDATED_DATE = "7 July 2026";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getLegalTranslator(locale);

  return {
    title: t("terms.title"),
    description: t("terms.description"),
    alternates: {
      canonical: `/${locale}/legal/terms`,
    },
  };
}

export default async function TermsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getLegalTranslator(locale);

  const sections = SECTION_IDS.map((id) => ({
    id,
    heading: t(`terms.sections.${id}.heading`),
    body: t(`terms.sections.${id}.body`),
  }));

  return (
    <LegalShell
      title={t("terms.title")}
      updatedLabel={t("updated", { date: UPDATED_DATE })}
      counselNote={t("counselNote")}
      tocLabel={t("onThisPage")}
      sections={sections}
    />
  );
}
