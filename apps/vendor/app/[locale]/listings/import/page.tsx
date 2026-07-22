import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ImportFlow } from "./_components/import-flow";

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
  const listings = vendorMessages.listings as {
    import: { meta: { title: string; description: string } };
  };
  return {
    title: listings.import.meta.title,
    description: listings.import.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function ListingsImportPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ImportFlow />
    </main>
  );
}
