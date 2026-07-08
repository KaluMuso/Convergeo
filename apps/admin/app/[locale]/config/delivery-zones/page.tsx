import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { ConfigPageShell } from "../_components/ConfigPageShell";
import { DeliveryZoneEditor } from "../_components/DeliveryZoneEditor";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function DeliveryZonesConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="delivery-zones"
      titleKey="deliveryZones.title"
      subtitleKey="deliveryZones.subtitle"
    >
      <DeliveryZoneEditor />
    </ConfigPageShell>
  );
}
