import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { DashboardsView } from "../_components/dashboards-view";

import type { Metadata } from "next";

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

/** Analytics — growth counts by Lusaka day. */
export default async function AnalyticsGrowthPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardsView locale={locale} tab="growth" />;
}
