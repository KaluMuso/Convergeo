import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { createLoginLabels } from "../../../../../customer/app/[locale]/(auth)/_components/auth-labels";
import { AuthLoginShell } from "../../../../../customer/app/[locale]/(auth)/_components/login-shell";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AdminLoginPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const commonMessages = await loadNamespace(locale as Locale, "common");
  const messages = {
    ...baseMessages,
    auth: authMessages,
    common: commonMessages,
  } as AbstractIntlMessages;

  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const labels = createLoginLabels(locale, messages, { variant: "admin" });

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="flex items-center justify-center px-4 py-6">
        <p className="font-display text-lg text-display-ink">{tCommon("app.name")}</p>
      </header>
      <main className="mx-auto flex w-full max-w-[360px] flex-1 flex-col px-4 pb-8">
        <AuthLoginShell
          locale={locale}
          variant="admin"
          labels={labels}
          defaultNextPath={`/${locale}`}
          nextParam={next}
          showSignupLink={false}
          phoneEnabled={false}
        />
      </main>
    </div>
  );
}
