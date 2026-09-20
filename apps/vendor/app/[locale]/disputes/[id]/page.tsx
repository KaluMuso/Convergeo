import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorDisputeDetailView } from "../_components/dispute-detail";

import type { Metadata } from "next";

/**
 * Protected, per-dispute route — always rendered per request.
 *
 * This segment carries TWO dynamic params (`[locale]` and `[id]`), but the page
 * exported a `generateStaticParams()` that could never enumerate `id`, so
 * Next.js classified the route static.
 *
 * This one was worse than the locale-only exports on its siblings: it pinned a
 * single all-zero dummy UUID (`00000000-0000-0000-0000-000000000000`),
 * prerendering a dispute that does not exist while every real dispute id fell
 * through to that same static shell.
 *
 * `id` is an arbitrary dispute UUID: there is no enumerable set, so no
 * `generateStaticParams()` on this segment can be correct. The shared vendor
 * locale layout also resolves nav capabilities per request — `cookies()`, an
 * authenticated Supabase `auth.getUser()` and `cache: "no-store"` API probes —
 * so a static classification here is the same "Page changed from static to
 * dynamic at runtime" defect already proven live on /[locale]/orders/[id] and
 * /[locale]/events/[id]/scan in staging run 35456698878. Dispute data is
 * owner-scoped and must never be prerendered or cached.
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
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <VendorDisputeDetailView disputeId={id} />
    </main>
  );
}
