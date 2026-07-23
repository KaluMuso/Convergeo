import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ServiceEditView } from "./_components/service-edit-view";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const vendor = servicesMessages.vendor as {
    form: { editTitle: string };
  };
  return {
    title: vendor.form.editTitle,
    robots: { index: false, follow: false },
  };
}

export default async function EditServicePage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ServiceEditView locale={locale} serviceId={id} />
    </main>
  );
}
