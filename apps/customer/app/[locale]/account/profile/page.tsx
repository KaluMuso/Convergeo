import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { fetchStorefrontConfig } from "../../../../lib/storefront-config";
import { createAccountApiClient, type Birthday } from "../_components/account-api";
import { getAccountAccessToken, getAccountTranslator } from "../_components/account-server";
import { BirthdayForm, type BirthdayLabels } from "../_components/birthday-form";
import { ProfileForm } from "../_components/profile-form";

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
  // Optional birthday treat (flag `birthday_greetings`). A stored birthday stays
  // visible even with the flag off so the customer can always remove it.
  const config = await fetchStorefrontConfig();
  let birthday: Birthday | null = null;
  try {
    birthday = await api.getBirthday();
  } catch {
    birthday = null;
  }
  const showBirthday = config.birthdays || Boolean(birthday?.consented);

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
          updated: String(t.raw("profile.updated")),
          error: t("profile.error"),
          locales: {
            en: t("locales.en"),
            bem: t("locales.bem"),
            nya: t("locales.nya"),
            fr: t("locales.fr"),
          },
        }}
      />
      {showBirthday ? (
        <BirthdayForm
          accessToken={accessToken}
          initial={birthday}
          labels={t.raw("birthday") as BirthdayLabels}
        />
      ) : null}
    </section>
  );
}
