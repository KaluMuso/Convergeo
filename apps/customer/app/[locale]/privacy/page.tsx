import { LOCALES, type Locale } from "@vergeo/i18n";
import { permanentRedirect } from "next/navigation";

import type { Metadata } from "next";

/**
 * LB-L08 — `/privacy` was a live 404. Canonical policy lives at `/legal/privacy`
 * (footer already points there). Permanent redirect preserves bookmarks/search.
 */
type PageProps = {
  params: Promise<{ locale: string }>;
};

export const metadata: Metadata = {
  robots: { index: false, follow: true },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function PrivacyAliasPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    permanentRedirect("/en/legal/privacy");
  }
  permanentRedirect(`/${locale}/legal/privacy`);
}
