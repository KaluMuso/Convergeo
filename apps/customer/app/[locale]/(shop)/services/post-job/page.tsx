import { loadNamespace, type Locale } from "@vergeo/i18n";
import { buildCanonicalAlternates } from "@vergeo/ui/src/seo/json-ld";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { PostJobForm } from "./post-job-form";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ category?: string }>;
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
    robots: { index: false, follow: false },
  };
}

export default async function PostJobPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { category } = await searchParams;
  setRequestLocale(locale);
  const servicesMessages = await loadNamespace(locale as Locale, "services");

  return (
    <div className="py-6 lg:mx-auto lg:w-full lg:max-w-2xl">
      <NextIntlClientProvider locale={locale} messages={{ services: servicesMessages }}>
        <PostJobForm locale={locale} initialCategory={category} />
      </NextIntlClientProvider>
    </div>
  );
}
