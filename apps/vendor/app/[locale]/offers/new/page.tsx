import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { isBundlesRouteAccessible } from "../../../../lib/route-capabilities";
import { OfferForm } from "../_components/offer-form";

import type { Metadata } from "next";

/** Flag-gated (`bundles`) and owner-scoped: always rendered per request. */
export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = (await loadNamespace(
    (LOCALES.includes(locale as Locale) ? locale : "en") as Locale,
    "vendor",
  )) as { offers: { form: { createTitle: string } } };
  return { title: vendor.offers.form.createTitle, robots: { index: false, follow: false } };
}

export default async function NewOfferPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  if (!(await isBundlesRouteAccessible())) {
    notFound();
  }
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <OfferForm locale={locale} mode="create" />
    </main>
  );
}
