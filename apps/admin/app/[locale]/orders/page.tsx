import { LOCALES } from "@vergeo/i18n";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { OrderSearch } from "./_components/OrderSearch";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function OrdersPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.orders");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <OrderSearch locale={locale} />
    </div>
  );
}
