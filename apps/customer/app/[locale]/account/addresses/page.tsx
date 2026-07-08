import { LOCALES, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { createAccountApiClient } from "../_components/account-api";
import { getAccountAccessToken, getAccountTranslator } from "../_components/account-server";
import { AddressManager } from "../_components/address-manager";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountAddressesPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const t = await getAccountTranslator(locale);
  const api = createAccountApiClient(() => accessToken);
  const addresses = await api.listAddresses();

  const formLabels = {
    label: t("addresses.label"),
    labelPlaceholder: t("addresses.labelPlaceholder"),
    landmark: t("addresses.landmark"),
    landmarkPlaceholder: t("addresses.landmarkPlaceholder"),
    landmarkHelp: t("addresses.landmarkHelp"),
    phone: t("addresses.phone"),
    phonePlaceholder: t("addresses.phonePlaceholder"),
    latitude: t("addresses.latitude"),
    longitude: t("addresses.longitude"),
    coordsHelp: t("addresses.coordsHelp"),
    useGps: t("addresses.useGps"),
    gpsLoading: t("addresses.gpsLoading"),
    gpsDenied: t("addresses.gpsDenied"),
    gpsUnavailable: t("addresses.gpsUnavailable"),
    mapPreview: t("addresses.mapPreview"),
    mapAlt: t("addresses.mapAlt"),
    mapEmpty: t("addresses.mapEmpty"),
    coordsTemplate: t("addresses.coordsTemplate"),
    save: t("addresses.save"),
    saving: t("addresses.saving"),
    cancel: t("addresses.cancel"),
    requiredLandmark: t("addresses.requiredLandmark"),
    error: t("addresses.error"),
    required: t("common.required"),
  };

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("addresses.title")}</h2>
        <p className="text-sm text-text-2">{t("addresses.description")}</p>
      </header>
      <AddressManager
        locale={locale}
        accessToken={accessToken}
        initialAddresses={addresses}
        labels={{
          ...formLabels,
          add: t("addresses.add"),
          edit: t("addresses.edit"),
          emptyTitle: t("addresses.emptyTitle"),
          emptyBody: t("addresses.emptyBody"),
          countLabel: t("addresses.count", { count: addresses.length }),
          coordsTemplate: t("addresses.coordsTemplate"),
          delete: t("addresses.delete"),
          deleteConfirmTitle: t("addresses.deleteConfirmTitle"),
          deleteConfirmBody: t("addresses.deleteConfirmBody"),
          saved: t("addresses.saved"),
        }}
      />
    </section>
  );
}
