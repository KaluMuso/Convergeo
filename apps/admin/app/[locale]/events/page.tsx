import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { AdvanceDebts } from "./_components/AdvanceDebts";
import { HighValueQueue } from "./_components/HighValueQueue";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function HighValueEventsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.events");

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <HighValueQueue />
      <AdvanceDebts />
    </AdminPage>
  );
}
