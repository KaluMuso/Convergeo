import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorReviewsQueue } from "./_components/vendor-reviews-queue";

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
  const reviews = vendorMessages.reviews as { meta: { title: string; description: string } };
  return {
    title: reviews.meta.title,
    description: reviews.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorReviewsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <VendorReviewsQueue />
    </main>
  );
}
