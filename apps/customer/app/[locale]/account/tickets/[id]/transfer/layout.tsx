import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Client i18n provider for the ticket-transfer page. The transfer page is a
 * client component calling useTranslations("events.transfer"); the root
 * provider only carries `common`, so the `events` namespace must be supplied
 * explicitly here or the page renders raw keys with MISSING_MESSAGE errors.
 */
export default async function TicketTransferLayout({ children, params }: LayoutProps) {
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
