import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../_components/vendor-page";

import { OnboardingFlow } from "./_components/onboarding-flow";

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
    meta: { title: string; description: string };
  };
  return {
    title: onboarding.meta.title,
    description: onboarding.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function OnboardingPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <VendorPage width="form">
      <OnboardingFlow locale={locale} />
    </VendorPage>
  );
}
