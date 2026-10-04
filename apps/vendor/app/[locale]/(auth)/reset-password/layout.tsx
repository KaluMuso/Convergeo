import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function PasswordRecoveryLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const [baseMessages, auth, common] = await Promise.all([
    getMessages(),
    loadNamespace(locale as Locale, "auth"),
    loadNamespace(locale as Locale, "common"),
  ]);
  const messages = { ...baseMessages, auth, common } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "common" });

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <div className="flex min-h-dvh flex-col bg-bg">
        <header className="flex items-center justify-center px-4 py-6">
          <p className="font-display text-lg text-display-ink">{t("app.name")}</p>
        </header>
        <main className="mx-auto flex w-full max-w-[360px] flex-1 flex-col px-4 pb-8">
          {children}
        </main>
      </div>
    </NextIntlClientProvider>
  );
}
