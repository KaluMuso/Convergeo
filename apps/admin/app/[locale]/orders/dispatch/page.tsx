import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../../lib/admin-translator";
import { DispatchBoard } from "../_components/DispatchBoard";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function DispatchBoardPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.dispatch");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <Link
          href={`/${locale}/orders`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
        >
          {t("back")}
        </Link>
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <DispatchBoard />
    </div>
  );
}
