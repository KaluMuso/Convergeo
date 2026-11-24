import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { socialContactsEnabled } from "../../../../lib/social/flag-server";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function PeopleLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  if (!(await socialContactsEnabled())) {
    notFound();
  }
  const socialMessages = await loadNamespace(locale as Locale, "social");
  return (
    <NextIntlClientProvider locale={locale} messages={{ social: socialMessages }}>
      <div data-testid="people-layout">{children}</div>
    </NextIntlClientProvider>
  );
}
