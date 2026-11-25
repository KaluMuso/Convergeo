import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";

import { KycReviewDetail } from "../_components/KycReviewDetail";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export default async function KycReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <KycReviewDetail locale={locale} kycId={id} />;
}
