import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { VendorPlansEditor } from "../_components/VendorPlansEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function VendorPlansConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="vendor-plans"
      titleKey="vendorPlans.title"
      subtitleKey="vendorPlans.subtitle"
    >
      <VendorPlansEditor />
    </ConfigPageShell>
  );
}
