import { LOCALES, type Locale } from "@vergeo/i18n";
import { permanentRedirect } from "next/navigation";

import type { Metadata } from "next";

/**
 * LB-L08 — `/terms` was a live 404. Canonical terms live at `/legal/terms`
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

export default async function TermsAliasPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    permanentRedirect("/en/legal/terms");
  }
  permanentRedirect(`/${locale}/legal/terms`);
}
