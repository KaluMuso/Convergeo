import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { VendorPlansEditor } from "../_components/VendorPlansEditor";

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

export default async function VendorPlansConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="vendor-plans"
      titleKey="vendorPlans.title"
      subtitleKey="vendorPlans.subtitle"
    >
      <VendorPlansEditor />
    </ConfigPageShell>
  );
}
