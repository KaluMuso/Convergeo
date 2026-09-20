import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { OrderDetailView } from "../_components/action-bar";

import type { Metadata } from "next";

/**
 * Protected, per-order route — always rendered per request.
 *
 * This segment has TWO dynamic params (`[locale]` and `[id]`), but the page
 * used to export a `generateStaticParams()` that enumerated only the locales.
 * Next.js treats a partial param set as a static-generation instruction, so
 * the route was classified static and the authenticated, `no-store` order
 * request that `OrderDetailView` issues at runtime tripped "Page changed from
 * static to dynamic at runtime" — the HTTP 500 observed on the Vendor preview
 * for /en/orders/{id} in staging run 35456698878.
 *
 * `id` is an arbitrary order UUID, so there is no enumerable set to prestate
 * and no correct `generateStaticParams()` for this segment: the only honest
 * classification is dynamic. Order data is owner-scoped and must never be
 * cached or prerendered, so forcing dynamic is also the correct privacy
 * posture, not merely a build-time fix.
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
  const orders = vendorMessages.orders as { meta: { title: string; description: string } };
  return {
    title: orders.meta.title,
    description: orders.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorOrderDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <OrderDetailView orderId={id} />
    </main>
  );
}
