import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminHubCard } from "../_components/admin-hub-card";
import { AdminPage } from "../_components/admin-page";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Configuration hub — shell nav targets `/config`, while editors live on
 * concrete subroutes. Read-only navigation only; no invented settings UI.
 */
export default async function ConfigHubPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.hubs.config");

  const destinations = [
    {
      key: "flags",
      href: `/${locale}/config/flags`,
      title: t("flagsTitle"),
      body: t("flagsBody"),
    },
    {
      key: "commissions",
      href: `/${locale}/config/commissions`,
      title: t("commissionsTitle"),
      body: t("commissionsBody"),
    },
    {
      key: "delivery",
      href: `/${locale}/config/delivery-zones`,
      title: t("deliveryTitle"),
      body: t("deliveryBody"),
    },
    {
      key: "categories",
      href: `/${locale}/config/categories`,
      title: t("categoriesTitle"),
      body: t("categoriesBody"),
    },
    {
      key: "platform",
      href: `/${locale}/config/platform`,
      title: t("platformTitle"),
      body: t("platformBody"),
    },
    {
      key: "vendorPlans",
      href: `/${locale}/config/vendor-plans`,
      title: t("vendorPlansTitle"),
      body: t("vendorPlansBody"),
    },
  ] as const;

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")} data-testid="admin-config-hub">
      <ul className="grid list-none gap-3 p-0 sm:grid-cols-2">
        {destinations.map((item) => (
          <li key={item.key}>
            <AdminHubCard href={item.href} title={item.title} body={item.body} hue="slate" />
          </li>
        ))}
      </ul>
    </AdminPage>
  );
}
