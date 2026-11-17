import { LOCALES } from "@vergeo/i18n";
import { notFound, redirect } from "next/navigation";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export const metadata: Metadata = {
  robots: { index: false, follow: true },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * "Browse" is the storefront entry point, not a page of its own: the label lives in
 * the navigation, and the category index is where browsing starts. This route exists
 * so `/{locale}/browse` (old links, typed URLs, the header label) never 404s.
 */
export default async function BrowsePage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as (typeof LOCALES)[number])) {
    notFound();
  }
  redirect(`/${locale}/categories`);
}
