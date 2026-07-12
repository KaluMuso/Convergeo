import { LOCALES } from "@vergeo/i18n";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { KycQueue } from "./_components/KycQueue";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function KycQueuePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("admin.kyc");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>
      <KycQueue locale={locale} />
    </div>
  );
}
