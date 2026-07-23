import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { RosterView } from "./_components/roster-view";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const eventRoster = vendorMessages.eventRoster as {
    meta: { title: string; description: string };
  };
  return {
    title: eventRoster.meta.title,
    description: eventRoster.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EventRosterPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <RosterView locale={locale} eventId={id} />
    </main>
  );
}
