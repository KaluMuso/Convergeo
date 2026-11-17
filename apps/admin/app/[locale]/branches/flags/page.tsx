import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { FlagsBoard } from "../_components/FlagsBoard";

type PageProps = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function BranchFlagsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.branches.flags");
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <FlagsBoard />
    </div>
  );
}
