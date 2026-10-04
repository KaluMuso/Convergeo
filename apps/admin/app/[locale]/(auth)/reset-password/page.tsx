import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ResetRequestForm } from "../../../../../customer/app/[locale]/(auth)/_components/reset-request-form";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AdminResetPasswordPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  return <ResetRequestForm locale={locale} />;
}
