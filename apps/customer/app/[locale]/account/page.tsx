import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { createAccountApiClient } from "./_components/account-api";
import { getAccountAccessToken, getAccountTranslator } from "./_components/account-server";
import { ProfileForm } from "./_components/profile-form";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountProfilePage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const t = await getAccountTranslator(locale);
  const api = createAccountApiClient(() => accessToken);
  const profile = await api.getProfile();

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("profile.title")}</h2>
        <p className="text-sm text-text-2">{t("profile.description")}</p>
      </header>
      <ProfileForm
        locale={locale}
        accessToken={accessToken}
        initialProfile={profile}
        labels={{
          nameLabel: t("profile.nameLabel"),
          namePlaceholder: t("profile.namePlaceholder"),
          localeLabel: t("profile.localeLabel"),
          phoneLabel: t("profile.phoneLabel"),
          phoneHelp: t("profile.phoneHelp"),
          save: t("profile.save"),
          saving: t("profile.saving"),
          updated: t("profile.updated"),
          error: t("profile.error"),
          locales: {
            en: t("locales.en"),
            bem: t("locales.bem"),
            nya: t("locales.nya"),
            fr: t("locales.fr"),
          },
        }}
      />
    </section>
  );
}
