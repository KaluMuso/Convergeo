import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type AuthLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function AuthLayout({ children, params }: AuthLayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const commonMessages = await loadNamespace(locale as Locale, "common");
  const messages = { ...baseMessages, common: commonMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "common" });

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="flex items-center justify-center px-4 py-6">
        <p className="font-display text-lg text-display-ink">{t("app.name")}</p>
        <span className="sr-only">{locale}</span>
      </header>
      <main className="mx-auto flex w-full max-w-[360px] flex-1 flex-col px-4 pb-8">
        {children}
      </main>
    </div>
  );
}
