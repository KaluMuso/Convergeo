import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { DashboardBoard } from "./_components/DashboardBoard";

type PageProps = {
  params: Promise<{ locale: string }>;
};

type DashboardTranslator = (key: string) => string;

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function HomePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const adminMessages = await loadNamespace(locale as Locale, "admin");
  const t = createTranslator({
    locale,
    messages: { admin: adminMessages } as AbstractIntlMessages,
    namespace: "admin.dashboard",
  }) as unknown as DashboardTranslator;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <DashboardBoard locale={locale} />
    </div>
  );
}
