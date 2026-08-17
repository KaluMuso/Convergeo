import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { FxRateEditor } from "../_components/FxRateEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function FxConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell locale={locale} active="fx" titleKey="fx.title" subtitleKey="fx.subtitle">
      <FxRateEditor />
    </ConfigPageShell>
  );
}
