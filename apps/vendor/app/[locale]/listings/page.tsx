import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ListingsManageList } from "./_components/listings-manage-list";

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
  const manage = vendorMessages.listings as {
    manage: { meta: { title: string; description: string } };
  };
  return {
    title: manage.manage.meta.title,
    description: manage.manage.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function ListingsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-0 sm:p-4">
      <ListingsManageList locale={locale} />
    </main>
  );
}
