import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { CatalogControlBoard } from "./_components/CatalogControlBoard";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function CatalogControlPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.catalog");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <CatalogControlBoard locale={locale} />
    </AdminPage>
  );
}
