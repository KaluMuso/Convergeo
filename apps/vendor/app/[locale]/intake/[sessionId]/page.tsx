import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { isIntakeRouteAccessible } from "../../../../lib/route-capabilities";
import { IntakeReview } from "../_components/intake-review";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; sessionId: string }>;
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

export default async function IntakeReviewPage({ params }: PageProps) {
  const { locale, sessionId } = await params;
  setRequestLocale(locale);

  if (!(await isIntakeRouteAccessible())) {
    notFound();
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-0 sm:p-4">
      <IntakeReview locale={locale} sessionId={sessionId} />
    </main>
  );
}
