import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { PlatformEditor } from "../_components/PlatformEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function PlatformConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="platform"
      titleKey="platform.title"
      subtitleKey="platform.subtitle"
    >
      <PlatformEditor />
    </ConfigPageShell>
  );
}
