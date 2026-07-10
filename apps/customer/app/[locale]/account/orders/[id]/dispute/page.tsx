import { ApiError, createApiClient } from "@vergeo/config";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../../../_components/account-server";
import { createOrdersApiClient } from "../../_components/orders-api";

import { DisputePageView } from "./_components/dispute-view";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

export default async function AccountOrderDisputePage({ params }: PageProps) {
  const { locale, id: orderId } = await params;

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

  const ordersApi = createOrdersApiClient(() => accessToken);
  try {
    await ordersApi.getOrder(orderId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  let initialDispute = null;
  const apiClient = createApiClient({
    baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    getToken: () => accessToken,
  });
  try {
    initialDispute = await apiClient.request<{
      id: string;
      order_id: string;
      status: string;
      evidence_paths: string[];
      vendor_response: string | null;
      admin_decision: string | null;
      timeline: Array<{
        from_status: string | null;
        to_status: string;
        note: string | null;
        actor: string | null;
        at: string;
      }>;
    }>(`/disputes/orders/${orderId}`);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) {
      throw error;
    }
  }

  const labels = {
    title: t("dispute.title"),
    body: t("dispute.body"),
    holdTrust: t("dispute.holdTrust"),
    statusLabel: t("dispute.statusLabel"),
    evidenceLabel: t("dispute.evidenceLabel"),
    evidenceHelp: t("dispute.evidenceHelp"),
    addEvidence: t("dispute.addEvidence"),
    uploading: t("dispute.uploading"),
    descriptionLabel: t("dispute.descriptionLabel"),
    descriptionPlaceholder: t("dispute.descriptionPlaceholder"),
    submit: t("dispute.submit"),
    submitting: t("dispute.submitting"),
    success: t("dispute.success"),
    error: t("dispute.error"),
    back: t("dispute.back"),
    timelineTitle: t("dispute.timelineTitle"),
    statusOpen: t("dispute.status.open"),
    statusVendorResponded: t("dispute.status.vendor_responded"),
    statusUnderReview: t("dispute.status.under_review"),
    statusResolvedRefund: t("dispute.status.resolved_refund"),
    statusResolvedRelease: t("dispute.status.resolved_release"),
    statusResolvedPartial: t("dispute.status.resolved_partial"),
    statusRejected: t("dispute.status.rejected"),
  };

  return (
    <DisputePageView
      locale={locale}
      orderId={orderId}
      accessToken={accessToken}
      initialDispute={initialDispute}
      labels={labels}
    />
  );
}
