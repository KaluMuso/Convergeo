import { LOCALES, type Locale } from "@vergeo/i18n";
import { redirect } from "next/navigation";

import type { Metadata } from "next";

/**
 * CUST-10 — calendar was a dead claim (`/en/calendar` 404). Event date browsing
 * already lives on `/events` (date chips + `calendar_dates` from the API), so
 * this route permanently redirects there instead of inventing a second surface.
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

export default async function CalendarPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    redirect("/en/events?date_window=all");
  }
  redirect(`/${locale}/events?date_window=all`);
}
