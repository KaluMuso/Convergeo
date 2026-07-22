import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ListingCreateFlow } from "./_components/listing-create-flow";

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
  const listings = vendorMessages.listings as { meta: { title: string; description: string } };
  return {
    title: listings.meta.title,
    description: listings.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function NewListingPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ListingCreateFlow locale={locale} />
    </main>
  );
}
