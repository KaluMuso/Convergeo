import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { IntakeSessionList } from "./_components/intake-session-list";

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
  const intake = vendorMessages.intake as {
    meta: { title: string; description: string };
  };
  return {
    title: intake.meta.title,
    description: intake.meta.description,
    robots: { index: false, follow: false },
  };
}

export default async function IntakePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-0 sm:p-4">
      <IntakeSessionList locale={locale} />
    </main>
  );
}
