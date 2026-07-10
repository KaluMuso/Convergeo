import { loadNamespace, type Locale } from "@vergeo/i18n";
import { buildCanonicalAlternates } from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { PostJobForm } from "./post-job-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

type ServicesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getServicesTranslator(locale: string): Promise<ServicesTranslator> {
  const baseMessages = await getMessages();
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const messages = { ...baseMessages, services: servicesMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "services",
  }) as unknown as ServicesTranslator;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getServicesTranslator(locale);
  const title = t("postJob.title");
  const description = t("postJob.subtitle");

  return {
    title,
    description,
    alternates: buildCanonicalAlternates(locale, "services", "post-job"),
  };
}

export default async function PostJobPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const servicesMessages = await loadNamespace(locale as Locale, "services");

  return (
    <main className="px-4 py-6">
      <NextIntlClientProvider locale={locale} messages={{ services: servicesMessages }}>
        <PostJobForm locale={locale} />
      </NextIntlClientProvider>
    </main>
  );
}
