import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { IntakeDetailPanel } from "../_components/IntakeDetailPanel";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function IntakeDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <IntakeDetailPanel locale={locale} sessionId={id} />;
}
