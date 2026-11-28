import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { VendorPageSkeleton } from "../_components/page-skeleton";
import { VendorPage } from "../_components/vendor-page";

import { SourceHub } from "./_components/source-hub";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

type SourceMessages = { title: string; intro: string };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const source = vendor.source as SourceMessages;
  return { title: source.title, robots: { index: false, follow: false } };
}

export default async function SourcePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const source = vendor.source as SourceMessages;
  return (
    <VendorPage width="full">
      <header className="space-y-1">
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">{source.title}</h1>
        <p className="m-0 text-sm text-text-2">{source.intro}</p>
      </header>
      <Suspense fallback={<VendorPageSkeleton rows={4} />}>
        <SourceHub />
      </Suspense>
    </VendorPage>
  );
}
