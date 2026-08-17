import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ClassDReadinessPanel } from "../_components/ClassDReadinessPanel";
import { ConfigPageShell } from "../_components/ConfigPageShell";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function ClassDConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="class-d"
      titleKey="classD.title"
      subtitleKey="classD.subtitle"
    >
      <ClassDReadinessPanel />
    </ConfigPageShell>
  );
}
