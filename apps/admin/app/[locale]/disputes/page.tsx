import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../lib/admin-translator";

import { DisputeQueue } from "./_components/DisputeQueue";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "disputes");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function DisputesQueuePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.disputes");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-display text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("subtitle")}</p>
      </header>
      <DisputeQueue locale={locale} />
    </div>
  );
}
