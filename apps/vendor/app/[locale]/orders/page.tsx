import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { OrdersQueueView } from "./_components/order-card";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ status?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendorMessages = await loadNamespace(locale as Locale, "vendor");
  const queue = vendorMessages.queue as { meta: { title: string; description: string } };
  return {
    title: queue.meta.title,
    description: queue.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function VendorOrdersQueuePage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { status } = await searchParams;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <OrdersQueueView locale={locale} initialStatus={status ?? "needs_action"} />
    </main>
  );
}
