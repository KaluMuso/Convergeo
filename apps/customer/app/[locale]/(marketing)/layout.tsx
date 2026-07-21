import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { MarketingAppHeader } from "./_components/marketing-app-header";

type MarketingLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Marketing routes keep per-page `<main id="marketing-main">` landmarks.
 * This layout adds unified AppHeader chrome and a keyboard skip link into that landmark.
 */
export default async function MarketingLayout({ children, params }: MarketingLayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return <>{children}</>;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const [commonMessages, navMessages] = await Promise.all([
    loadNamespace(locale as Locale, "common"),
    loadNamespace(locale as Locale, "nav"),
  ]);
  const messages = {
    ...baseMessages,
    common: commonMessages,
    nav: navMessages,
  } as AbstractIntlMessages;
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tNav = createTranslator({ locale, messages, namespace: "nav" });

  return (
    <>
      <a
        href="#marketing-main"
        className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
      >
        {tNav("skipToContent")}
      </a>
      <MarketingAppHeader
        locale={locale}
        labels={{
          appName: tCommon("app.name"),
          navAriaLabel: tNav("marketing.ariaLabel"),
          about: tNav("marketing.about"),
          contact: tNav("marketing.contact"),
          help: tNav("marketing.help"),
          sell: tNav("marketing.sell"),
          signIn: tNav("marketing.signIn"),
        }}
      />
      {children}
    </>
  );
}
