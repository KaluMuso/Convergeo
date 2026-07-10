import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

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
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
      <VendorHomeView locale={locale} />
    </main>
  );
}
