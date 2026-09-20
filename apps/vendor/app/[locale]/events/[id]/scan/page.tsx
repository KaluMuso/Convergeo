import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ScannerView } from "./_components/scanner-view";

import type { Metadata } from "next";

/**
 * Protected organiser check-in scanner — always rendered per request.
 *
 * Same defect and same reasoning as the order detail route: the segment has
 * TWO dynamic params (`[locale]` and `[id]`) while `generateStaticParams()`
 * enumerated only the locales, so Next.js classified the route static and the
 * authenticated, `no-store` event request `ScannerView` issues at runtime
 * tripped "Page changed from static to dynamic at runtime" — the HTTP 500
 * observed on the Vendor preview for /en/events/{id}/scan in staging run
 * 35456698878.
 *
 * `id` is an arbitrary event UUID with no enumerable set, and the scanner
 * surface is organiser-scoped ticket state that must never be prerendered or
 * cached, so dynamic is the only correct classification.
 *
 * apps/vendor/app/protected-dynamic-routes.test.ts pins this contract.
 */
export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

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
