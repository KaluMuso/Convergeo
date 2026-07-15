import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { AccountNav } from "./_components/account-nav";
import { requireAuthenticatedAccount } from "./_components/account-server";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type AccountLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function AccountLayout({ children, params }: AccountLayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  await requireAuthenticatedAccount(locale);

  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const messages = { ...baseMessages, account: accountMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account" });

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8">
      <header className="mb-2">
        <h1 className="font-display text-h1 text-display-ink">{t("title")}</h1>
      </header>
      <AccountNav
        locale={locale}
        labels={{
          ariaLabel: t("title"),
          profile: t("nav.profile"),
          addresses: t("nav.addresses"),
          preferences: t("nav.preferences"),
          business: t("nav.business"),
          privacy: t("nav.privacy"),
        }}
      />
      {children}
    </div>
  );
}
