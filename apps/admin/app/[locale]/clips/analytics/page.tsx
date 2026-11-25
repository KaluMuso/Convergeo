import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { ClipAnalyticsPanel } from "../_components/ClipAnalyticsPanel";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "clips");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ClipAnalyticsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.clips.analytics");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("intro")}</p>
      </header>
      <ClipAnalyticsPanel />
    </div>
  );
}
