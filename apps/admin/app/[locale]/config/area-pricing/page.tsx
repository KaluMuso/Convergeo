import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { AreaPricingEditor } from "../_components/AreaPricingEditor";
import { ConfigPageShell } from "../_components/ConfigPageShell";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "config");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AreaPricingConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="area-pricing"
      titleKey="areaPricing.title"
      subtitleKey="areaPricing.subtitle"
    >
      <AreaPricingEditor />
    </ConfigPageShell>
  );
}
