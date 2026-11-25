import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { DashboardsView } from "../_components/dashboards-view";

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

/** Analytics — services (RFQs, quotes, bookings) and events (tickets, check-ins). */
export default async function AnalyticsServicesEventsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardsView locale={locale} tab="servicesEvents" />;
}
