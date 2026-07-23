import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorDisputesListView } from "./_components/disputes-list";

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
  const disputes = vendorMessages.disputes as { meta: { title: string; description: string } };
  return {
    title: disputes.meta.title,
    description: disputes.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorDisputesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <VendorDisputesListView />
    </main>
  );
}
