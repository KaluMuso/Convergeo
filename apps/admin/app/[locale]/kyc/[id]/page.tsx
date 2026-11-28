import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { KycReviewDetail } from "../_components/KycReviewDetail";

import type { Metadata } from "next";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "kyc");
}

export default async function KycReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <KycReviewDetail locale={locale} kycId={id} />;
}
