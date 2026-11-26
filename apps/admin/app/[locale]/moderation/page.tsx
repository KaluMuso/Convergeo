import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import type { Metadata } from "next";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";

import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { ModerationDestinations } from "./moderation-destinations";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "moderation");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Moderation hub — the shell nav links here, but work lives on subroutes.
 * Keeps Access-authenticated admins from hitting a 404 after the Moderation tab.
 */
export default async function ModerationHubPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.hubs.moderation");

  const destinations = [
    {
      key: "products",
      href: `/${locale}/moderation/products`,
      title: t("productsTitle"),
      body: t("productsBody"),
    },
    {
      key: "canonical",
      href: `/${locale}/moderation/products#canonical`,
      title: t("canonicalTitle"),
      body: t("canonicalBody"),
    },
    {
      key: "flags",
      href: `/${locale}/moderation/flags`,
      title: t("flagsTitle"),
      body: t("flagsBody"),
    },
  ] as const;

  return (
    <AdminPage title={t("title")} subtitle={t("subtitle")} data-testid="admin-moderation-hub">
      <ModerationDestinations destinations={destinations} />
    </AdminPage>
  );
}
