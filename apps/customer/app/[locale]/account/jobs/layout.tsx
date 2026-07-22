import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Client i18n provider for the account "jobs" (services RFQ) subtree. Client
 * pages here — e.g. jobs/[id] and its accept/complete/review flows — call
 * useTranslations("services.*"), which the root provider (`common` only) does
 * not carry, so the `services` namespace must be supplied explicitly or every
 * key renders as a MISSING_MESSAGE console error.
 */
export default async function AccountJobsLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const services = await loadNamespace(locale as Locale, "services");
  return (
    <NextIntlClientProvider locale={locale} messages={{ services }}>
      {children}
    </NextIntlClientProvider>
  );
}
