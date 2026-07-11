import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { AnalyticsView } from "./_components/analytics-view";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const analytics = vendorMessages.analytics as {
    meta: { title: string; description: string };
  };
  return {
    title: analytics.meta.title,
    description: analytics.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function AnalyticsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <AnalyticsView />
    </main>
  );
}
