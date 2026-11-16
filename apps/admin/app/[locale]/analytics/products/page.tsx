import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { AnalyticsView } from "../_components/analytics-view";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/** Convergeo Intelligence 1B-05 — analytics (products). Aggregates only; flag-gated by the API. */
export default async function AnalyticsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <AnalyticsView locale={locale} tab="products" />;
}
