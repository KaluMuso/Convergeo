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
    <section className="space-y-4 rounded-lg border border-[#E8DFD0] bg-white p-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-[#2A2118]">{t("title")}</h2>
        <p className="text-sm text-[#6B5E4C]">
          {t("summary", {
            name: card.customer.display_name ?? t("unknownName"),
            phone: card.customer.phone ?? t("unknownPhone"),
          })}
        </p>
      </header>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[#6B5E4C]">{t("customerId")}</dt>
          <dd className="font-mono text-xs text-[#2A2118]">{card.customer.id}</dd>
        </div>
        <div>
          <dt className="text-[#6B5E4C]">{t("openOrders")}</dt>
          <dd className="text-[#2A2118]">{card.open_orders_count}</dd>
        </div>
        <div>
          <dt className="text-[#6B5E4C]">{t("latestStatus")}</dt>
          <dd className="text-[#2A2118]">
            {card.latest_order_status
              ? t(`statuses.${card.latest_order_status}` as "statuses.placed")
              : t("noOrders")}
          </dd>
        </div>
        <div>
          <dt className="text-[#6B5E4C]">{t("locale")}</dt>
          <dd className="text-[#2A2118]">{card.customer.locale}</dd>
        </div>
      </dl>

      {card.orders.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-[#2A2118]">{t("recentOrders")}</h3>
          <ul className="space-y-2">
            {card.orders.map((order) => (
              <li key={order.id} className="rounded-md border border-[#F0E9DE] px-3 py-2 text-sm">
                <div className="font-mono text-xs text-[#6B5E4C]">{order.id}</div>
                <div className="font-medium text-[#2A2118]">{order.vendor_display_name}</div>
                <div className="text-xs text-[#6B5E4C]">
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
