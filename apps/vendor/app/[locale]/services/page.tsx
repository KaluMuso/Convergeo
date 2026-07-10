import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ServicesManageList } from "./_components/services-manage-list";

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
    list: { title: string; intro: string };
  };
  return {
    title: vendor.list.title,
    description: vendor.list.intro,
    robots: { index: false, follow: false },
  };
}

export default async function ServicesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <ServicesManageList locale={locale} />
    </main>
  );
}
