import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../_components/vendor-page";

import { BusinessesOverview } from "./_components/businesses-overview";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const branches = vendor.branches as { title: string };
  return { title: branches.title, robots: { index: false, follow: false } };
}

export default async function BusinessesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const branches = vendor.branches as { title: string; intro: string };
  return (
    <VendorPage width="full">
      <header className="space-y-1">
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{branches.title}</h1>
        <p className="m-0 text-sm text-text-2">{branches.intro}</p>
      </header>
      <BusinessesOverview locale={locale} />
    </VendorPage>
  );
}
