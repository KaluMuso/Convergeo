import { setRequestLocale } from "next-intl/server";

import { BranchReview } from "../_components/BranchReview";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ locale: string; id: string }> };

export default async function BranchReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <BranchReview locale={locale} branchId={id} />;
}
