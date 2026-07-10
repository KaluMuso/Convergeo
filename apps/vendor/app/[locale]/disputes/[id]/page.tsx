import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorDisputeDetailView } from "../_components/dispute-detail";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const disputes = vendorMessages.disputes as { meta: { title: string; description: string } };
  return {
    title: disputes.meta.title,
    description: disputes.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorDisputeDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <VendorDisputeDetailView disputeId={id} />
    </main>
  );
}
