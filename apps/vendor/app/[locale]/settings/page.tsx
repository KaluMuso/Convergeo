import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../_components/vendor-page";

import { SettingsView } from "./_components/settings-view";

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
  const settings = vendorMessages.settings as { meta: { title: string; description: string } };
  return {
    title: settings.meta.title,
    description: settings.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function SettingsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <VendorPage width="form">
      <SettingsView locale={locale} />
    </VendorPage>
  );
}
