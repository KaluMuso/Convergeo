import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { isBundlesRouteAccessible } from "../../../../../lib/route-capabilities";
import { OfferEditView } from "../../_components/offer-edit-view";

import type { Metadata } from "next";

/**
 * Protected, per-offer route — `id` is an arbitrary UUID and the data is
 * owner-scoped, so it is never prerendered (see protected-dynamic-routes.test.ts).
 */
export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = (await loadNamespace(
    (LOCALES.includes(locale as Locale) ? locale : "en") as Locale,
    "vendor",
  )) as { offers: { form: { editTitle: string } } };
  return { title: vendor.offers.form.editTitle, robots: { index: false, follow: false } };
}

export default async function EditOfferPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  if (!(await isBundlesRouteAccessible())) {
    notFound();
  }
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <OfferEditView locale={locale} offerId={id} />
    </main>
  );
}
