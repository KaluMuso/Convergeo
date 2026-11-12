import { randomUUID } from "node:crypto";

import { LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { getAccountAccessToken } from "../../_components/account-server";
import { QuoteDetailClient } from "../_components/quote-detail-client";

import type { RfqThread } from "../../../../../lib/rfq-api";
import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

async function fetchThread(accessToken: string, threadId: string): Promise<RfqThread | null> {
  const base = getApiBaseUrl();
  if (!base) {
    return null;
  }
  const response = await fetch(`${base}/rfq/${encodeURIComponent(threadId)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as RfqThread;
}

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountListingQuoteDetailPage({ params }: PageProps) {
  const { locale, id } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const thread = await fetchThread(accessToken, id);

  if (thread === null || thread.listing_id === null) {
    notFound();
  }

  return <QuoteDetailClient locale={locale} threadId={id} refreshKey={randomUUID()} />;
}
