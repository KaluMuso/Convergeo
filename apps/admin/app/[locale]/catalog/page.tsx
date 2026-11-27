import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";
import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { CatalogControlBoard } from "./_components/CatalogControlBoard";

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

export default async function CatalogControlPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.catalog");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <p className="mb-3">
        <Link
          href={`/${locale}/catalog/categories`}
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-text"
          data-testid="catalog-categories-link"
        >
          {t("manageCategories")}
        </Link>
      </p>
      <CatalogControlBoard locale={locale} />
    </AdminPage>
  );
}
