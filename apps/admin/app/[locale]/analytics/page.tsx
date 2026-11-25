import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { DashboardsView } from "./_components/dashboards-view";

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

/** Analytics — users: registrations, active users (v2, flag-gated) and purchase retention. */
export default async function AnalyticsUsersPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardsView locale={locale} tab="users" />;
}
