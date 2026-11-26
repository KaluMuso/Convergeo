import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../../lib/admin-page-metadata";
import { ConfigPageShell } from "../_components/ConfigPageShell";
import { PlatformEditor } from "../_components/PlatformEditor";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "config");
}

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
