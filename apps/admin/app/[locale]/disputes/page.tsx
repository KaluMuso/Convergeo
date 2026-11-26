import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

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
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <DisputeQueue locale={locale} />
    </AdminPage>
  );
}
