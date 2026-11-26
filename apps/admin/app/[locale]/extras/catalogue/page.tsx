import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { AdminPage } from "../../_components/admin-page";
import { ExtrasCatalogueEditor } from "../_components/ExtrasCatalogueEditor";

type PageProps = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ExtrasCataloguePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.extras.catalogue");
  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")}>
      <ExtrasCatalogueEditor />
    </AdminPage>
  );
}
