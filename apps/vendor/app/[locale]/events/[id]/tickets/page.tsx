import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { TicketTypeConfig } from "./_components/ticket-type-config";

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
  const tickets = vendorMessages.tickets as {
    meta: { title: string; description: string };
  };
  return {
    title: tickets.meta.title,
    description: tickets.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EventTicketsPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <TicketTypeConfig locale={locale} eventId={id} />
    </main>
  );
}
