import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { setRequestLocale } from "next-intl/server";

import { getLegalTranslator, LegalShell } from "../_components/legal-shell";

import type { Metadata } from "next";
import type { ReactNode } from "react";

const SECTION_IDS = [
  "introduction",
  "controller",
  "dataCollected",
  "legalBasis",
  "use",
  "sharing",
  "retention",
  "security",
  "dataRights",
  "cookies",
  "children",
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
    title: t("privacy.title"),
    description: t("privacy.description"),
    alternates: {
      canonical: `/${locale}/legal/privacy`,
    },
  };
}

export default async function PrivacyPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getLegalTranslator(locale);

  const sections = SECTION_IDS.map((id) => ({
    id,
    heading: t(`privacy.sections.${id}.heading`),
    body:
      id === "dataRights"
        ? t.rich(`privacy.sections.${id}.body`, {
            link: (chunks: ReactNode) => (
              <Link
                className="font-medium text-primary underline underline-offset-2"
                href={`/${locale}/account/data`}
              >
                {chunks}
              </Link>
            ),
          })
        : t(`privacy.sections.${id}.body`),
  }));

  return (
    <LegalShell
      title={t("privacy.title")}
      updatedLabel={t("updated", { date: UPDATED_DATE })}
      counselNote={t("counselNote")}
      tocLabel={t("onThisPage")}
      sections={sections}
    />
  );
}
