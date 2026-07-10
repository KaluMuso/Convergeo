import { setRequestLocale } from "next-intl/server";

import { OrderDetailView } from "../_components/OrderDetailView";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export default async function OrderDetailPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <OrderDetailView locale={locale} orderId={id} />;
}
