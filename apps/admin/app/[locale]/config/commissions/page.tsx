import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { CommissionEditor } from "../_components/CommissionEditor";
import { ConfigPageShell } from "../_components/ConfigPageShell";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function CommissionsConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="commissions"
      titleKey="commissions.title"
      subtitleKey="commissions.subtitle"
    >
      <CommissionEditor />
    </ConfigPageShell>
  );
}
