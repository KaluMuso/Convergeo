"use client";

import { useTranslations } from "next-intl";

import { type ContextCard } from "./api";

type ContextCardViewProps = {
  card: ContextCard;
  locale: string;
};

export function ContextCardView({ card, locale }: ContextCardViewProps) {
  const t = useTranslations("admin.support.context");

  return (
    <section className="space-y-4 rounded-lg border border-border bg-surface p-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-text">{t("title")}</h2>
        <p className="text-sm text-muted">
          {t("summary", {
            name: card.customer.display_name ?? t("unknownName"),
            phone: card.customer.phone ?? t("unknownPhone"),
          })}
        </p>
      </header>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">{t("customerId")}</dt>
          <dd className="font-mono text-xs text-text">{card.customer.id}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("openOrders")}</dt>
          <dd className="text-text">{card.open_orders_count}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("latestStatus")}</dt>
          <dd className="text-text">
            {card.latest_order_status
              ? t(`statuses.${card.latest_order_status}` as "statuses.placed")
              : t("noOrders")}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("locale")}</dt>
          <dd className="text-text">{card.customer.locale}</dd>
        </div>
      </dl>

      {card.orders.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-text">{t("recentOrders")}</h3>
          <ul className="space-y-2">
            {card.orders.map((order) => (
              <li key={order.id} className="rounded-md border border-border px-3 py-2 text-sm">
                <div className="font-mono text-xs text-muted">{order.id}</div>
                <div className="font-medium text-text">{order.vendor_display_name}</div>
                <div className="text-xs text-muted">
                  {t("orderLine", {
                    status: t(`statuses.${order.status}` as "statuses.placed"),
                    date: new Date(order.created_at).toLocaleString(locale),
                  })}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
