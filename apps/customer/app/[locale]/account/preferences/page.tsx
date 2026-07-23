import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { createAccountApiClient } from "../_components/account-api";
import {
  getAccountAccessToken,
  getAccountTranslator,
  getLocaleSwitcherLabels,
} from "../_components/account-server";
import { PreferencesForm } from "../_components/preferences-form";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountPreferencesPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const t = await getAccountTranslator(locale);
  const localeSwitcherLabels = await getLocaleSwitcherLabels(locale);
  const api = createAccountApiClient(() => accessToken);
  const preferences = await api.getPreferences();

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("preferences.title")}</h2>
        <p className="text-sm text-text-2">{t("preferences.description")}</p>
      </header>
      <PreferencesForm
        accessToken={accessToken}
        locale={locale}
        initialPrefs={preferences.notif_prefs}
        localeSwitcherLabels={localeSwitcherLabels}
        labels={{
          themeTitle: t("preferences.themeTitle"),
          themeDescription: t("preferences.themeDescription"),
          themeLight: t("preferences.themeLight"),
          themeDark: t("preferences.themeDark"),
          themeSystem: t("preferences.themeSystem"),
          notificationsTitle: t("preferences.notificationsTitle"),
          whatsapp: t("preferences.whatsapp"),
          whatsappHelp: t("preferences.whatsappHelp"),
          sms: t("preferences.sms"),
          smsHelp: t("preferences.smsHelp"),
          email: t("preferences.email"),
          emailHelp: t("preferences.emailHelp"),
          save: t("preferences.save"),
          saving: t("preferences.saving"),
          saved: t("preferences.saved"),
          error: t("preferences.error"),
        }}
      />
    </section>
  );
}
