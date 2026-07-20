import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { AuthBrandHeader } from "./_components/auth-brand-header";

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
  const [commonMessages, authMessages] = await Promise.all([
    loadNamespace(locale as Locale, "common"),
    loadNamespace(locale as Locale, "auth"),
  ]);
  const messages = {
    ...baseMessages,
    common: commonMessages,
    auth: authMessages,
  } as AbstractIntlMessages;
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tAuth = createTranslator({ locale, messages, namespace: "auth" });

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <a
        href="#auth-main"
        className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
      >
        {tCommon("nav.skipToContent")}
      </a>
      <AuthBrandHeader appName={tCommon("app.name")} tagline={tAuth("chrome.customerTagline")} />
      <span className="sr-only">{locale}</span>
      <main
        id="auth-main"
        tabIndex={-1}
        className="relative z-10 mx-auto -mt-5 flex w-full max-w-[400px] flex-1 flex-col px-4 pb-8 focus-visible:outline-none"
      >
        <div className="motion-rise rounded-lg border border-border bg-surface p-5 shadow-2 sm:p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
