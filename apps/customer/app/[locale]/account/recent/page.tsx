import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAccountTranslator } from "../_components/account-server";

import { RecentlyViewedPanel } from "./_components/recently-viewed-panel";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountRecentPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const t = await getAccountTranslator(locale);

  return (
    <RecentlyViewedPanel
      locale={locale}
      labels={{
        title: t("recent.title"),
        description: t("recent.description"),
        privacyNote: t("recent.privacyNote"),
        emptyTitle: t("recent.emptyTitle"),
        emptyBody: t("recent.emptyBody"),
        browseCta: t("recent.browseCta"),
        clear: t("recent.clear"),
        clearing: t("recent.clearing"),
        loading: t("common.loading"),
        remove: t("recent.remove"),
        removeLabel: t("recent.removeLabel"),
        viewProduct: t("recent.viewProduct"),
      }}
    />
  );
}
