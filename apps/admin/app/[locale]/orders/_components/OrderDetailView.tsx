"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { payoutsEnabled } from "../../../../lib/payout-posture";
import { useAdminPermissions } from "../../../../lib/roles-api";
import { CopyButton } from "../../_components/CopyButton";
import { LoadingBlock } from "../../_components/StateBlocks";

import { type OrderDetail, ordersApi } from "./api";
import { DeliveryCard } from "./DeliveryCard";
import { type Board } from "./dispatch-board-model";
import { DispatchPanel } from "./DispatchPanel";
import { EscrowPanel } from "./EscrowPanel";
import { InterventionPanel } from "./InterventionPanel";
import { allowedAdminActions, isDispatchEvent } from "./order-transitions";
import { OrderStatusStepper } from "./OrderStatusStepper";
import { OrderTimeline } from "./OrderTimeline";

type OrderDetailViewProps = {
  locale: string;
  orderId: string;
};

export function OrderDetailView({ locale, orderId }: OrderDetailViewProps) {
  const canMutate = useAdminPermissions()?.unrestricted === true;
  const t = useTranslations("admin.orders.detail");
  const funding = useTranslations("services.funding");
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [board, setBoard] = useState<Board | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await ordersApi.request<OrderDetail>(`/admin/orders/${orderId}`);
      setOrder(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
    // Address, rider and COD come from the dispatch board; the order stays usable without it.
    try {
      setBoard(await ordersApi.request<Board>("/admin/dispatch/board"));
    } catch {
      setBoard(null);
    }
  }, [orderId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <LoadingBlock label={t("loading")} rows={4} />;
  }

  if (error || !order) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-danger">
          {error ?? t("error")}
        </p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => {
            setLoading(true);
            void load();
          }}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  const guard = {
    status: order.status,
    fulfilment: order.fulfilment,
    cod: order.cod,
    paid: order.payments.some((payment) => payment.status === "success"),
  };
  const dispatchEvents = allowedAdminActions(guard)
    .map((action) => action.event)
    .filter(isDispatchEvent);
  const payoutsOn = payoutsEnabled();

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

      <OrderStatusStepper status={order.status} fulfilment={order.fulfilment} />

      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="break-all font-mono text-sm text-text">{order.id}</h1>
          <CopyButton value={order.id} label={t("copyOrderId")} />
        </div>
        <p className="text-sm text-muted">
          {t("summary", {
            vendor: order.vendor_display_name,
            customer: order.customer_display_name ?? order.customer_phone ?? "—",
            fulfilment: t(`fulfilment.${order.fulfilment}`),
          })}
        </p>
      </header>

      {canMutate ? (
        <InterventionPanel
          order={order}
          guard={guard}
          payoutsOn={payoutsOn}
          onSuccess={() => void load()}
        />
      ) : null}

      <DeliveryCard locale={locale} order={order} board={board} />

      {canMutate && dispatchEvents.length > 0 ? (
        <DispatchPanel
          key={dispatchEvents.join(",")}
          order={order}
          events={dispatchEvents}
          onSuccess={() => void load()}
        />
      ) : null}

      {Boolean(order.service_obligations?.length) && (
        <section className="space-y-2">
          <h2>{funding("title")}</h2>
          {order.service_obligations?.map((leg) => (
            <p key={leg.id}>
              {funding(leg.leg)}: {formatK(leg.amount_ngwee)} — {funding(`status.${leg.status}`)}
              <span className="block font-mono text-xs">{leg.checkout_group_id}</span>
            </p>
          ))}
        </section>
      )}

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
                  <span>
                    {t("paymentLine", {
                      rail: payment.rail,
                      status: payment.status,
                    })}
                  </span>
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

      {canMutate ? (
        <details className="rounded-lg border border-border bg-surface p-4">
          <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-text">
            {t("advancedEscrow")}
          </summary>
          <div className="pt-3">
            <EscrowPanel order={order} onSuccess={() => void load()} />
          </div>
        </details>
      ) : null}
    </div>
  );
}
