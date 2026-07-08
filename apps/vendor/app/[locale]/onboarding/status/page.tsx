import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { StatusPageClient } from "./status-client";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const onboarding = vendorMessages.onboarding as {
    meta: { description: string };
    status: { heading: string };
  };
  return {
    title: onboarding.status.heading,
    description: onboarding.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function OnboardingStatusPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <StatusPageClient locale={locale} />;
}
