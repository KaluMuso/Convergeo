import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ListingEditForm } from "./_components/listing-edit-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const manage = vendorMessages.listings as {
    manage: { edit: { meta: { title: string; description: string } } };
  };
  return {
    title: manage.manage.edit.meta.title,
    description: manage.manage.edit.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EditListingPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ListingEditForm locale={locale} listingId={id} />
    </main>
  );
}
