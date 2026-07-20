import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { AccountOverview } from "./_components/account-overview";
import { getAccountTranslator } from "./_components/account-server";

type PageProps = {
  params: Promise<{ locale: string }>;
};

type AccountMessages = {
  hub?: {
    savedCount?: string;
  };
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountOverviewPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const t = await getAccountTranslator(locale);
  // Client fills `{count}` — avoid ICU format at translate time.
  const accountMessages = (await loadNamespace(locale as Locale, "account")) as AccountMessages;
  const savedCountTemplate = accountMessages.hub?.savedCount ?? "{count}";

  return (
    <AccountOverview
      locale={locale}
      labels={{
        title: t("hub.title"),
        description: t("hub.description"),
        ordersTitle: t("hub.ordersTitle"),
        ordersBody: t("hub.ordersBody"),
        ordersCta: t("hub.ordersCta"),
        savedTitle: t("hub.savedTitle"),
        savedEmpty: t("hub.savedEmpty"),
        savedCount: savedCountTemplate,
        savedCta: t("hub.savedCta"),
        recentTitle: t("hub.recentTitle"),
        recentEmpty: t("hub.recentEmpty"),
        recentCta: t("hub.recentCta"),
        addressesTitle: t("hub.addressesTitle"),
        addressesBody: t("hub.addressesBody"),
        addressesCta: t("hub.addressesCta"),
        preferencesTitle: t("hub.preferencesTitle"),
        preferencesBody: t("hub.preferencesBody"),
        preferencesCta: t("hub.preferencesCta"),
        helpTitle: t("hub.helpTitle"),
        helpBody: t("hub.helpBody"),
        helpCta: t("hub.helpCta"),
        deviceNote: t("hub.deviceNote"),
      }}
    />
  );
}
