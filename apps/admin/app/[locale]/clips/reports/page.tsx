import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { ClipReportsQueue } from "../_components/ClipReportsQueue";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ClipReportsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.clips.reports");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("intro")}</p>
      </header>
      <ClipReportsQueue />
    </div>
  );
}
