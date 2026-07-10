import { LOCALES } from "@vergeo/i18n";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { MerchBoard } from "./_components/MerchBoard";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function MerchPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.merch");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-[#2A2118]">{t("title")}</h1>
        <p className="text-sm text-[#6B5E4C]">{t("subtitle")}</p>
      </header>
      <MerchBoard locale={locale} />
    </div>
  );
}
