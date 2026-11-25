import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { ClipDecisionPanel } from "../_components/ClipDecisionPanel";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "clips");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ClipReviewDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <ClipDecisionPanel clipId={id} locale={locale} />;
}
