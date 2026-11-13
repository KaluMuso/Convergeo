import { loadNamespace, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { isIntakeRouteAccessible } from "../../../../lib/route-capabilities";
import { IntakeReview } from "../_components/intake-review";

import type { Metadata } from "next";

/**
 * Protected, per-session vendor intake review — always rendered per request.
 *
 * Last of the Vendor routes carrying a non-locale dynamic segment. Same defect
 * class as the ten `[id]` routes repaired before it: the page exported a
 * `generateStaticParams()` supplying only the locale while the segment also
 * carries `[sessionId]`, so Next.js classified the route static.
 *
 * Here the page body itself is unambiguously request-specific:
 * `isIntakeRouteAccessible()` reads `cookies()`, resolves the feature flag,
 * calls `supabase.auth.getUser()` and then reads the vendor row and the
 * `waha_intake_vendor_allowlist` platform config — an authenticated capability
 * check on every render. Prerendering that is the "Page changed from static to
 * dynamic at runtime" condition already proven live on /[locale]/orders/[id]
 * and /[locale]/events/[id]/scan in staging run 35456698878.
 *
 * The feature flag being off today does not make it safe: with the route
 * static, a direct hit risks that runtime failure instead of the clean,
 * fail-closed 404 the `notFound()` below is meant to produce. `sessionId` is an
 * arbitrary intake-session id with no enumerable set, so no
 * `generateStaticParams()` on this segment can ever be correct.
 *
 * This changes rendering only. The flag, the allowlist, the capability check
 * and the 404 behaviour are untouched — the intake feature stays disabled.
 *
 * apps/vendor/app/protected-dynamic-routes.test.ts pins this contract.
 */
export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; sessionId: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const intake = vendorMessages.intake as {
    meta: { title: string; description: string };
  };
  return {
    title: intake.meta.title,
    description: intake.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function IntakeReviewPage({ params }: PageProps) {
  const { locale, sessionId } = await params;
  setRequestLocale(locale);

  if (!(await isIntakeRouteAccessible())) {
    notFound();
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-0 sm:p-4">
      <IntakeReview locale={locale} sessionId={sessionId} />
    </main>
  );
}
