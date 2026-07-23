import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ServiceForm } from "../_components/service-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const vendor = servicesMessages.vendor as {
    form: { createTitle: string };
  };
  return {
    title: vendor.form.createTitle,
    robots: { index: false, follow: false },
  };
}

export default async function NewServicePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <ServiceForm locale={locale} mode="create" />
    </main>
  );
}
