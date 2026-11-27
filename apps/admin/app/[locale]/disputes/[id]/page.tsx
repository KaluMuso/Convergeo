import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { DisputeReviewDetail } from "../_components/DisputeReviewDetail";

import type { Metadata } from "next";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "disputes");
}

export default async function DisputeReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <DisputeReviewDetail disputeId={id} locale={locale} />;
}
