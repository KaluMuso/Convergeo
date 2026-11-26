import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Client i18n provider for event-team accept. The form is client-side and calls
 * useTranslations("events.teamAccept"); the account layout only supplies
 * account/orders/nav, so events must be loaded here.
 */
export default async function EventTeamAcceptLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const events = await loadNamespace(locale as Locale, "events");
  return (
    <NextIntlClientProvider locale={locale} messages={{ events }}>
      {children}
    </NextIntlClientProvider>
  );
}
