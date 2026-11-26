import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { IntakeQueue } from "./_components/IntakeQueue";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "intake");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function IntakeQueuePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.intake");

  return (
    <AdminPage title={t("title")} subtitle={t("intro")}>
      <IntakeQueue locale={locale} />
    </AdminPage>
  );
}
