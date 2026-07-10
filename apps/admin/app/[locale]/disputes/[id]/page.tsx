import { setRequestLocale } from "next-intl/server";

import { DisputeReviewDetail } from "../_components/DisputeReviewDetail";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export default async function DisputeReviewPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <DisputeReviewDetail disputeId={id} locale={locale} />;
}
