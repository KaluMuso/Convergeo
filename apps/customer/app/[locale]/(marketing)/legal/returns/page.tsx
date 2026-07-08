import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getLegalTranslator, LegalShell } from "../_components/legal-shell";

import type { Metadata } from "next";

const SECTION_IDS = [
  "introduction",
  "lane1",
  "lane1Steps",
  "lane2",
  "lane2Refund",
  "lane2Steps",
  "escrow",
  "exclusions",
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
    title: t("returns.title"),
    description: t("returns.description"),
    alternates: {
      canonical: `/${locale}/legal/returns`,
    },
  };
}

export default async function ReturnsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getLegalTranslator(locale);

  const sections = SECTION_IDS.map((id) => ({
    id,
    heading: t(`returns.sections.${id}.heading`),
    body: t(`returns.sections.${id}.body`),
  }));

  return (
    <LegalShell
      title={t("returns.title")}
      updatedLabel={t("updated", { date: UPDATED_DATE })}
      counselNote={t("counselNote")}
      tocLabel={t("onThisPage")}
      sections={sections}
    />
  );
}
