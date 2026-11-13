import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { EventDashboard } from "./_components/event-dashboard";

import type { Metadata } from "next";

/**
 * Protected, per-event route — always rendered per request.
 *
 * This segment carries TWO dynamic params (`[locale]` and `[id]`), but the page
 * exported a `generateStaticParams()` that could never enumerate `id`, so
 * Next.js classified the route static.
 *
 * `id` is an arbitrary event UUID: there is no enumerable set, so no
 * `generateStaticParams()` on this segment can be correct. The shared vendor
 * locale layout also resolves nav capabilities per request — `cookies()`, an
 * authenticated Supabase `auth.getUser()` and `cache: "no-store"` API probes —
 * so a static classification here is the same "Page changed from static to
 * dynamic at runtime" defect already proven live on /[locale]/orders/[id] and
 * /[locale]/events/[id]/scan in staging run 35456698878. Event data is
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
  const eventDashboard = vendorMessages.eventDashboard as {
    meta: { title: string; description: string };
  };
  return {
    title: eventDashboard.meta.title,
    description: eventDashboard.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EventDashboardPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <EventDashboard locale={locale} eventId={id} />
    </main>
  );
}
