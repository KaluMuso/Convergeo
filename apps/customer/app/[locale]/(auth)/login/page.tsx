import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { createLoginLabels } from "../_components/auth-labels";
import { AuthLoginShell } from "../_components/login-shell";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ next?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function LoginPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { next } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const authMessages = await loadNamespace(locale as Locale, "auth");
  const messages = { ...baseMessages, auth: authMessages } as AbstractIntlMessages;

  const labels = createLoginLabels(locale, messages, { variant: "customer" });

  return (
    <AuthLoginShell
      locale={locale}
      variant="customer"
      labels={labels}
      defaultNextPath={`/${locale}`}
      nextParam={next}
      showSignupLink
    />
  );
}
