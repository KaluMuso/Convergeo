import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { buildPageMetadata } from "../../../../../lib/page-title";
import { ResetConfirmForm } from "../../_components/reset-confirm-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return buildPageMetadata(locale, "auth", "reset.confirmTitle");
}

export default async function ResetPasswordConfirmPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);

  return <ResetConfirmForm locale={locale} />;
}
