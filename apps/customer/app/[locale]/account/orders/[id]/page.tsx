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
