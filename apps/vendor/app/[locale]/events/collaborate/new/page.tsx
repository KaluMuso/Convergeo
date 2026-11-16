import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { CollabForm } from "../_components/collab-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

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

export default async function CollaborationPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col px-4 py-3">
      <CollabForm locale={locale} />
    </main>
  );
}
