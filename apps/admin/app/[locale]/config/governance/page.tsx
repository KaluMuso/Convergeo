import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { GovernanceEditor } from "../_components/GovernanceEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function GovernanceConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="governance"
      titleKey="governance.title"
      subtitleKey="governance.subtitle"
    >
      <GovernanceEditor />
    </ConfigPageShell>
  );
}
