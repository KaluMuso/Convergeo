import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { AnalyticsView } from "../_components/analytics-view";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "analytics");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/** Convergeo Intelligence 1B-05 — analytics (insights). Aggregates only; flag-gated by the API. */
export default async function AnalyticsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <AnalyticsView locale={locale} tab="insights" />;
}
