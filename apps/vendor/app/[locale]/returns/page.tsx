import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorReturnsQueue } from "./_components/returns-queue";

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
  const returns = vendorMessages.returns as { meta: { title: string; description: string } };
  return {
    title: returns.meta.title,
    description: returns.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorReturnsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <VendorReturnsQueue locale={locale} />
    </main>
  );
}
