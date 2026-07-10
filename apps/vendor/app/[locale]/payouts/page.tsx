import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { PayoutsView } from "./_components/payouts-view";

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
  const payouts = vendorMessages.payouts as { meta: { title: string; description: string } };
  return {
    title: payouts.meta.title,
    description: payouts.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function PayoutsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <PayoutsView locale={locale} />
    </main>
  );
}
