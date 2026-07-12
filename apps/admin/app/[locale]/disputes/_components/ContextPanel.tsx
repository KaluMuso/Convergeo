"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";

import type { OrderContext } from "./api";

type ContextPanelProps = {
  order: OrderContext;
  locale: string;
};

export function ContextPanel({ order, locale }: ContextPanelProps) {
  const t = useTranslations("admin.disputes.detail.context");

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-text">{t("summary")}</h3>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">{t("vendor")}</dt>
            <dd>{order.vendor_display_name}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("customer")}</dt>
            <dd>{order.customer_display_name ?? order.customer_phone ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("orderStatus")}</dt>
            <dd>{order.status}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("orderTotal")}</dt>
            <dd className="font-mono">{formatK(order.order_total_ngwee)}</dd>
          </div>
        </dl>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-text">{t("items")}</h3>
        {order.items.length === 0 ? (
          <p className="text-sm text-muted">{t("itemsEmpty")}</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {order.items.map((item) => (
              <li key={item.id}>
                {t("itemLine", {
                  title: item.title_snapshot ?? item.item_kind,
                  qty: item.qty,
                  price: formatK(item.unit_price_ngwee),
                })}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-text">{t("payments")}</h3>
        {order.payments.length === 0 ? (
          <p className="text-sm text-muted">{t("paymentsEmpty")}</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {order.payments.map((payment) => (
              <li key={payment.id} className="font-mono text-xs">
                {t("paymentLine", {
                  rail: payment.rail,
                  status: payment.status,
                  amount: formatK(payment.amount_ngwee),
                  at: new Date(payment.created_at).toLocaleString(locale),
                })}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-text">{t("ledger")}</h3>
        {order.ledger.length === 0 ? (
          <p className="text-sm text-muted">{t("ledgerEmpty")}</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {order.ledger.map((txn) => {
              const balance = txn.postings.reduce((sum, posting) => sum + posting.amount_ngwee, 0);
              return (
                <li key={txn.id} className="rounded-md border border-border p-2">
                  <p className="font-medium">{txn.kind}</p>
                  <p className="text-xs text-muted">
                    {new Date(txn.created_at).toLocaleString(locale)}
                  </p>
                  <p className="font-mono text-xs">{t("ledgerBalance", { balance })}</p>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
