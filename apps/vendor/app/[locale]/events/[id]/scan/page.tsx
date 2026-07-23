import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ScannerView } from "./_components/scanner-view";

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
  const scan = vendorMessages.scan as {
    eventCheckIn: { meta: { title: string; description: string } };
  };
  return {
    title: scan.eventCheckIn.meta.title,
    description: scan.eventCheckIn.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EventScanPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ScannerView eventId={id} />
    </main>
  );
}
