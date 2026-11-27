import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { setRequestLocale } from "next-intl/server";

import { adminNavPageMetadata } from "../../../lib/admin-page-metadata";
import { getAdminTranslator } from "../../../lib/admin-translator";
import { AdminPage } from "../_components/admin-page";

import { OrderSearch } from "./_components/OrderSearch";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  return adminNavPageMetadata(locale, "orders");
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function OrdersPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getAdminTranslator(locale, "admin.orders");

  return (
    <AdminPage
      title={t("title")}
      subtitle={t("subtitle")}
      actions={
        <Link
          href={`/${locale}/orders/dispatch`}
          className="inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-3 text-sm font-medium text-primary press-scale hover:border-primary"
        >
          {t("openDispatchBoard")}
        </Link>
      }
    >
      <OrderSearch locale={locale} />
    </AdminPage>
  );
}
