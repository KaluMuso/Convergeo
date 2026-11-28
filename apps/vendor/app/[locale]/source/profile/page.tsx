import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../../_components/vendor-page";

import { SupplierProfile } from "./_components/supplier-profile";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

type ProfileMessages = { title: string; intro: string };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const profile = (vendor.source as { profile: ProfileMessages }).profile;
  return { title: profile.title, robots: { index: false, follow: false } };
}

export default async function SourceProfilePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const profile = (vendor.source as { profile: ProfileMessages }).profile;
  return (
    <VendorPage width="form">
      <header className="space-y-1">
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{profile.title}</h1>
        <p className="m-0 text-sm text-text-2">{profile.intro}</p>
      </header>
      <SupplierProfile locale={locale} />
    </VendorPage>
  );
}
