import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { AdminPage } from "../../_components/admin-page";

import { DuplicateQueue } from "./_components/DuplicateQueue";
import { PendingCanonicalQueue } from "./_components/PendingCanonicalQueue";
import { RelatedProductsEditor } from "./_components/RelatedProductsEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "moderation");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ProductModerationPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.moderation");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <PendingCanonicalQueue locale={locale} />
      <hr className="border-border" />
      <DuplicateQueue />
      <hr className="border-border" />
      <RelatedProductsEditor />
    </AdminPage>
  );
}
