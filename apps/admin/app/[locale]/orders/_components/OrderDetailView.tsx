"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type OrderDetail, ordersApi } from "./api";
import { DispatchPanel } from "./DispatchPanel";
import { EscrowPanel } from "./EscrowPanel";
import { InterventionPanel } from "./InterventionPanel";
import { OrderTimeline } from "./OrderTimeline";

type OrderDetailViewProps = {
  locale: string;
  orderId: string;
};

export function OrderDetailView({ locale, orderId }: OrderDetailViewProps) {
  const t = useTranslations("admin.orders.detail");
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await ordersApi.request<OrderDetail>(`/admin/orders/${orderId}`);
      setOrder(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [orderId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  if (error || !order) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error ?? t("error")}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className="text-sm font-medium text-primary underline-offset-2 hover:underline"
          href={`/${locale}/orders`}
        >
          {t("back")}
        </Link>
        <span className="rounded-full bg-bg-2 px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted">
          {t(`statuses.${order.status}`)}
        </span>
      </div>

      <header className="space-y-1">
        <h1 className="font-mono text-sm text-text">{order.id}</h1>
        <p className="text-sm text-muted">
          {t("summary", {
            vendor: order.vendor_display_name,
            customer: order.customer_display_name ?? order.customer_phone ?? "—",
            fulfilment: t(`fulfilment.${order.fulfilment}`),
          })}
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="font-medium text-text">{t("itemsTitle")}</h2>
        <ul className="divide-y divide-border rounded-md border border-border">
          {order.items.map((item) => (
            <li key={item.id} className="flex justify-between gap-3 px-3 py-2 text-sm">
              <span>
                {t("itemLine", {
                  title: item.title_snapshot ?? item.item_kind,
                  qty: item.qty,
                })}
              </span>
              <span className="font-mono">{formatK(item.unit_price_ngwee * item.qty)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium text-text">{t("paymentsTitle")}</h2>
        {order.payments.length === 0 ? (
          <p className="text-sm text-muted">{t("paymentsEmpty")}</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {order.payments.map((payment) => (
              <li key={payment.id} className="px-3 py-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span>{t("paymentLine", { rail: payment.rail, status: payment.status })}</span>
                  <span className="font-mono">{formatK(payment.amount_ngwee)}</span>
                </div>
                <p className="font-mono text-xs text-muted">{payment.lenco_reference}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium text-text">{t("ledgerTitle")}</h2>
        {order.ledger.length === 0 ? (
          <p className="text-sm text-muted">{t("ledgerEmpty")}</p>
        ) : (
          <ul className="space-y-2">
            {order.ledger.map((txn) => {
              const balance = txn.postings.reduce((sum, posting) => sum + posting.amount_ngwee, 0);
              return (
                <li key={txn.id} className="rounded-md border border-border px-3 py-2 text-sm">
                  <div className="font-mono text-xs">{txn.kind}</div>
                  <div className="text-xs text-muted">{t("ledgerBalance", { balance })}</div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium text-text">{t("timelineTitle")}</h2>
        <OrderTimeline events={order.timeline} locale={locale} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <DispatchPanel order={order} onSuccess={() => void load()} />
        <InterventionPanel order={order} onSuccess={() => void load()} />
      </div>

      <EscrowPanel order={order} onSuccess={() => void load()} />
    </div>
  );
}
