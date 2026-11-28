import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { BranchReview } from "../_components/BranchReview";

import type { Metadata } from "next";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ locale: string; id: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "branches");
}

export default async function BranchReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <BranchReview locale={locale} branchId={id} />;
}
