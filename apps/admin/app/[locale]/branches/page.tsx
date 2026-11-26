import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { BranchQueue } from "./_components/BranchQueue";

type PageProps = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function BranchQueuePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.branches");
  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <BranchQueue locale={locale} />
    </AdminPage>
  );
}
