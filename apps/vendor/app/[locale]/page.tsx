import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { VendorPage } from "./_components/vendor-page";
import { VendorHomeView } from "./orders/_components/order-card";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function HomePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <VendorPage width="full">
      <VendorHomeView locale={locale} />
    </VendorPage>
  );
}
