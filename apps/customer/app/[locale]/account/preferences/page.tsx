import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { createAccountApiClient } from "../_components/account-api";
import { getAccountAccessToken, getAccountTranslator } from "../_components/account-server";
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
        initialPrefs={preferences.notif_prefs}
        labels={{
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
