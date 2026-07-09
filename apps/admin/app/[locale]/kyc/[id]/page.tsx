import { setRequestLocale } from "next-intl/server";

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
