import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";
import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { MerchBoard } from "./_components/MerchBoard";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "merch");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function MerchPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.merch");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <MerchBoard locale={locale} />
    </AdminPage>
  );
}
