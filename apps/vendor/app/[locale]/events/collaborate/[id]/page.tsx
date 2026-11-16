import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { CollabDetail } from "../_components/collab-detail";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

/** Owner-scoped, per-request route (see the contract in events/[id]/edit/page.tsx). */
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const events = vendorMessages.events as {
    collab: { meta: { title: string; description: string } };
  };
  return {
    title: events.collab.meta.title,
    description: events.collab.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function CollaborationRequestPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col px-4 py-3">
      <CollabDetail locale={locale} requestId={id} />
    </main>
  );
}
