import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Client i18n provider scoped to the card-payment return page. This page is a
 * client component calling useTranslations("checkout.card"), but the (shop)
 * provider only carries catalog/search/nav/common — so `checkout` must be
 * supplied here or the card-payment screen renders raw keys (a live conversion
 * path). Scoped to this route so the checkout namespace never ships on the
 * perf-budgeted public shop pages. `common` is included to match the namespaces
 * the (shop) provider otherwise supplies to shared UI on this route.
 */
export default async function CheckoutCardLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const [checkout, common] = await Promise.all([
    loadNamespace(locale as Locale, "checkout"),
    loadNamespace(locale as Locale, "common"),
  ]);
  return (
    <NextIntlClientProvider locale={locale} messages={{ checkout, common }}>
      {children}
    </NextIntlClientProvider>
  );
}
