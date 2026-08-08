import { ApiError } from "@vergeo/config";
import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../../_components/account-server";
import { InvoiceLinkBlock } from "../_components/invoice-link";
import { OrderTimeline } from "../_components/order-timeline";
import {
  createOrdersApiClient,
  type OrderDetail,
  type OrderItem,
  type OrderSummary,
} from "../_components/orders-api";
import { PickupCredentialsBlock } from "../_components/pickup-credentials";

import {
  buildDispatchStatusUpdates,
  DispatchTimeline,
  extractDispatchFromEvents,
  type DispatchOrderEvent,
} from "./_components/dispatch-timeline";
import { ConfirmReceivedBlock } from "./_components/confirm-received";
import { ReportProblemBlock } from "./_components/report-problem";
import { ReviewPromptBlock } from "./_components/review-prompt";
import { OrderPostDeliveryActions } from "./_components/order-post-delivery-actions";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale, id: "00000000-0000-0000-0000-000000000000" }));
}

export default async function AccountOrderDetailPage({ params }: PageProps) {
  const { locale, id } = await params;

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

  const timelineLabels = {
    title: t("timeline.title"),
    steps: {
      placed: t("timeline.placed"),
      paymentHeld: t("timeline.paymentHeld"),
      paymentCod: t("timeline.paymentCod"),
      confirmed: t("timeline.confirmed"),
      processing: t("timeline.processing"),
      ready: t("timeline.ready"),
      shipped: t("timeline.shipped"),
      delivered: t("timeline.delivered"),
      completed: t("timeline.completed"),
      cancelled: t("timeline.cancelled"),
      refunded: t("timeline.refunded"),
    },
    escrow: {
      held: t("escrow.held"),
      released: t("escrow.released"),
      refunded: t("escrow.refunded"),
      cod: t("escrow.cod"),
    },
  };

  const otherOrders = order.related_orders.filter(
    (related: OrderSummary) => related.id !== order.id,
  );

  const dispatchEvents =
    (order as OrderDetail & { dispatch_events?: DispatchOrderEvent[] }).dispatch_events ?? [];
  const dispatchDetails = extractDispatchFromEvents(dispatchEvents);

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link
          href={`/${locale}/account/orders`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
        >
          {t("detail.back")}
        </Link>
        <h2 className="font-display text-h2 text-display-ink">
          {t("detail.orderId", { id: order.id.slice(0, 8).toUpperCase() })}
        </h2>
        <p className="text-sm text-text-2">{t("detail.vendor", { vendor: order.vendor_name })}</p>
        <p className="text-sm text-text-2">
          {order.fulfilment === "pickup"
            ? t("detail.fulfilmentPickup")
            : t("detail.fulfilmentDelivery")}
          {" · "}
          {order.payment_mode === "cod" ? t("list.paymentCod") : t("list.paymentPrepaid")}
        </p>
      </header>

      <OrderTimeline timeline={order.timeline} labels={timelineLabels} />

      <DispatchTimeline
        fulfilment={order.fulfilment}
        status={order.status}
        courier={dispatchDetails.courier}
        trackingNote={dispatchDetails.trackingNote}
        statusUpdates={buildDispatchStatusUpdates(
          order.timeline,
          {
            processing: t("timeline.processing"),
            shipped: t("timeline.shipped"),
            delivered: t("timeline.delivered"),
          },
          dispatchEvents,
        )}
        labels={{
          title: t("dispatch.title"),
          courier: t("dispatch.courier"),
          tracking: t("dispatch.tracking"),
          empty: t("dispatch.empty"),
          statusUpdates: t("dispatch.statusUpdates"),
        }}
      />

      {order.pickup ? (
        <PickupCredentialsBlock
          pickup={order.pickup}
          labels={{
            title: t("pickup.title"),
            qrLabel: t("pickup.qrLabel"),
            pinLabel: t("pickup.pinLabel"),
            stubBody: t("pickup.stubBody"),
            pinAria: t("pickup.pinAria"),
          }}
        />
      ) : null}

      <section className="space-y-2 rounded border border-border bg-surface p-4">
        <h3 className="font-display text-h3 text-display-ink">{t("detail.title")}</h3>
        <ul className="divide-y divide-border">
          {order.items.map((item: OrderItem) => (
            <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-sm">
              <span className="text-display-ink">
                {t("detail.lineQty", { title: item.title, qty: item.qty })}
              </span>
              <span className="shrink-0 font-mono text-display-ink">
                {formatK(item.qty * item.unit_price_ngwee)}
              </span>
            </li>
          ))}
        </ul>
        <dl className="space-y-1 border-t border-border pt-3 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-text-2">{t("detail.subtotal")}</dt>
            <dd className="font-mono text-display-ink">{formatK(order.subtotal_ngwee)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-text-2">{t("detail.deliveryFee")}</dt>
            <dd className="font-mono text-display-ink">{formatK(order.delivery_fee_ngwee)}</dd>
          </div>
          <div className="flex justify-between gap-3 font-medium">
            <dt className="text-display-ink">{t("detail.total")}</dt>
            <dd className="font-mono text-display-ink">{formatK(order.total_ngwee)}</dd>
          </div>
        </dl>
      </section>

      <InvoiceLinkBlock
        invoice={order.invoice}
        labels={{
          title: t("invoice.title"),
          download: t("invoice.download"),
          stubHelp: t("invoice.stubHelp"),
          unavailable: t("invoice.unavailable"),
        }}
      />

      <ConfirmReceivedBlock
        orderId={order.id}
        accessToken={accessToken}
        status={order.status}
        labels={{
          title: t("confirm.title"),
          body: t("confirm.body"),
          trust: t("confirm.trust"),
          button: t("confirm.button"),
          confirming: t("confirm.confirming"),
          done: t("confirm.done"),
          doneBody: t("confirm.doneBody"),
          error: t("confirm.error"),
        }}
      />

      <ReportProblemBlock
        orderId={order.id}
        accessToken={accessToken}
        status={order.status}
        labels={{
          title: t("report.title"),
          body: t("report.body"),
          categoryLabel: t("report.categoryLabel"),
          categoryFaulty: t("report.categoryFaulty"),
          categoryWrong: t("report.categoryWrong"),
          categoryNotDelivered: t("report.categoryNotDelivered"),
          categoryOther: t("report.categoryOther"),
          descriptionLabel: t("report.descriptionLabel"),
          descriptionPlaceholder: t("report.descriptionPlaceholder"),
          evidenceLabel: t("report.evidenceLabel"),
          evidenceHelp: t("report.evidenceHelp"),
          addEvidence: t("report.addEvidence"),
          uploading: t("report.uploading"),
          submit: t("report.submit"),
          submitting: t("report.submitting"),
          successLane1: t("report.successLane1"),
          successDispute: t("report.successDispute"),
          successSupport: t("report.successSupport"),
          successGuidance: t("report.successGuidance"),
          error: t("report.error"),
          requiredDescription: t("report.requiredDescription"),
        }}
      />

      <ReviewPromptBlock
        orderId={order.id}
        accessToken={accessToken}
        status={order.status}
        labels={{
          title: t("reviewPrompt.title"),
          body: t("reviewPrompt.body"),
          itemLabel: t("reviewPrompt.itemLabel"),
          ratingLabel: t("reviewPrompt.ratingLabel"),
          starsAria: t("reviewPrompt.starsAria"),
          bodyLabel: t("reviewPrompt.bodyLabel"),
          bodyPlaceholder: t("reviewPrompt.bodyPlaceholder"),
          submit: t("reviewPrompt.submit"),
          submitting: t("reviewPrompt.submitting"),
          success: t("reviewPrompt.success"),
          error: t("reviewPrompt.error"),
          editNotice: t("reviewPrompt.editNotice"),
          loading: t("reviewPrompt.loading"),
          starFilled: t("reviewPrompt.starFilled"),
          starEmpty: t("reviewPrompt.starEmpty"),
        }}
      />

      <OrderPostDeliveryActions
        locale={locale}
        orderId={order.id}
        status={order.status}
        labels={{
          actionsTitle: t("detail.actionsTitle"),
          requestReturn: t("detail.requestReturn"),
          openDispute: t("detail.openDispute"),
        }}
      />

      {otherOrders.length > 0 ? (
        <section className="space-y-3">
          <h3 className="font-display text-h3 text-display-ink">{t("detail.relatedTitle")}</h3>
          <ul className="space-y-2">
            {otherOrders.map((related: OrderSummary) => (
              <li key={related.id}>
                <Link
                  href={`/${locale}/account/orders/${related.id}`}
                  className="flex min-h-11 items-center justify-between rounded border border-border bg-surface px-4 py-3 text-sm"
                >
                  <span>{related.vendor_name}</span>
                  <span className="font-mono">{formatK(related.total_ngwee)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
