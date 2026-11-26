import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { IntakeDetailPanel } from "../_components/IntakeDetailPanel";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "intake");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function IntakeDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <IntakeDetailPanel locale={locale} sessionId={id} />;
}
