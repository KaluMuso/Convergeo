import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { EventEditView } from "./_components/event-edit-view";

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
  const events = vendorMessages.events as {
    form: { editMeta: { title: string; description: string } };
  };
  return {
    title: events.form.editMeta.title,
    description: events.form.editMeta.description,
    robots: { index: false, follow: false },
  };
}

export default async function EditEventPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <EventEditView locale={locale} eventId={id} />
    </main>
  );
}
