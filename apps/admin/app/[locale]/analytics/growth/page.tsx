import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { DashboardsView } from "../_components/dashboards-view";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/** Analytics — growth counts by Lusaka day. */
export default async function AnalyticsGrowthPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardsView locale={locale} tab="growth" />;
}
