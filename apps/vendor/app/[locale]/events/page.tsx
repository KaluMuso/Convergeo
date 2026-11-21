import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "../_components/vendor-page";

import { EventsManageList } from "./_components/events-manage-list";

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
  const events = vendorMessages.events as {
    list: { meta: { title: string; description: string } };
  };
  return {
    title: events.list.meta.title,
    description: events.list.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EventsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <VendorPage width="full">
      <EventsManageList locale={locale} />
    </VendorPage>
  );
}
