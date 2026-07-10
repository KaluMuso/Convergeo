import { ApiError } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import dynamic from "next/dynamic";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../../../_components/account-server";
import {
  createOrdersApiClient,
  type OrderDetail,
  type OrderItem,
} from "../../_components/orders-api";

import type { Metadata } from "next";

const ReturnForm = dynamic(() => import("./_components/return-form").then((mod) => mod.ReturnForm));

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ item?: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

export default async function OrderReturnPage({ params, searchParams }: PageProps) {
  const { locale, id } = await params;
  const { item: itemQuery } = await searchParams;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const baseMessages = await getMessages();
  const ordersMessages = await loadNamespace(locale as Locale, "orders");
  const messages = { ...baseMessages, orders: ordersMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "orders" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const api = createOrdersApiClient(() => accessToken);

  let order: OrderDetail;
  try {
    order = await api.getOrder(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const orderItemId = itemQuery ?? order.items[0]?.id;
  const orderItem = order.items.find((item: OrderItem) => item.id === orderItemId);
  if (!orderItem) {
    notFound();
  }

  return (
    <section className="mx-auto w-full max-w-[360px] space-y-4 p-4">
      <Link
        href={`/${locale}/account/orders/${id}`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
      >
        {t("return.back")}
      </Link>

      <ReturnForm
        orderId={id}
        orderItemId={orderItem.id}
        accessToken={accessToken}
        labels={{
          title: t("return.title"),
          body: t("return.body"),
          lane1Title: t("return.lane1.title"),
          lane1Body: t("return.lane1.body"),
          lane2Title: t("return.lane2.title"),
          lane2Unavailable: t("return.lane2.unavailable"),
          evidenceLabel: t("return.evidence.label"),
          evidenceHelp: t("return.evidence.help"),
          addEvidence: t("return.evidence.add"),
          uploading: t("return.evidence.uploading"),
          breakdownTitle: t("return.breakdown.title"),
          breakdownItem: t("return.breakdown.item"),
          breakdownDelivery: t("return.breakdown.delivery"),
          breakdownTotal: t("return.breakdown.total"),
          windowExpired: t("return.windowExpired"),
          submit: t("return.submit"),
          submitting: t("return.submitting"),
          success: t("return.success"),
          error: t("return.error"),
          evidenceRequired: t("return.evidence.required"),
        }}
      />
    </section>
  );
}
