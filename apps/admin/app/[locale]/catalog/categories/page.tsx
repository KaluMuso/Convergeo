import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { getAdminTranslator } from "../../../../lib/admin-translator";
import { AdminPage } from "../../_components/admin-page";

import { CategoryManager } from "./_components/CategoryManager";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "catalog");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function CatalogCategoriesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.catalog.categories");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <CategoryManager />
    </AdminPage>
  );
}
