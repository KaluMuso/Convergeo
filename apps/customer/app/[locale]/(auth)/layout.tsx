import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { LocaleSwitcher } from "../_components/locale-switcher";

import { AuthHeader } from "./_components/auth-header";
import { AuthSlimFooter } from "./_components/auth-slim-footer";

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
  const [commonMessages, authMessages, navMessages, legalMessages] = await Promise.all([
    loadNamespace(locale as Locale, "common"),
    loadNamespace(locale as Locale, "auth"),
    loadNamespace(locale as Locale, "nav"),
    loadNamespace(locale as Locale, "legal"),
  ]);
  const messages = {
    ...baseMessages,
    common: commonMessages,
    auth: authMessages,
    nav: navMessages,
    legal: legalMessages,
  } as AbstractIntlMessages;
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tAuth = createTranslator({ locale, messages, namespace: "auth" });
  const tNav = createTranslator({ locale, messages, namespace: "nav" });
  const tLegal = createTranslator({ locale, messages, namespace: "legal" });
  const localeSwitcher = (
    <LocaleSwitcher
      locale={locale}
      variant="footer"
      labels={{
        ariaLabel: tCommon("locale.switchAria"),
        names: {
          en: tCommon("locale.names.en"),
          bem: tCommon("locale.names.bem"),
          nya: tCommon("locale.names.nya"),
          fr: tCommon("locale.names.fr"),
        },
      }}
    />
  );

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <div className="flex min-h-dvh flex-col bg-bg">
        <AuthHeader
          locale={locale}
          appName={tCommon("app.name")}
          tagline={tAuth("chrome.customerTagline")}
          skipToContent={tNav("skipToContent")}
          backToShopLabel={tNav("auth.backToShop")}
          localeSwitcher={localeSwitcher}
        />
        <span className="sr-only">{locale}</span>
        <main
          id="auth-main"
          tabIndex={-1}
          className="relative z-10 mx-auto -mt-5 flex w-full max-w-[400px] flex-1 flex-col px-4 pb-6 focus-visible:outline-none"
        >
          <div className="motion-rise rounded-lg border border-border bg-surface p-5 shadow-2 sm:p-6">
            {children}
          </div>
        </main>
        <AuthSlimFooter
          locale={locale}
          labels={{
            help: tLegal("footer.links.help"),
            privacy: tLegal("footer.links.privacy"),
            terms: tLegal("footer.links.terms"),
          }}
          localeSwitcher={localeSwitcher}
        />
      </div>
    </NextIntlClientProvider>
  );
}
