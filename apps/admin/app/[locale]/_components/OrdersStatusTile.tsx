"use client";

import { useTranslations } from "next-intl";

import { type OrdersByStatus } from "./api";
import { isOrdersPipelineEmpty } from "./dashboard-truth";
import { TileShell } from "./TileShell";

const STATUS_KEYS = [
  "placed",
  "confirmed",
  "processing",
  "ready",
  "shipped",
  "delivered",
  "completed",
  "cancelled",
] as const;

type OrdersStatusTileProps = {
  ordersByStatus: OrdersByStatus;
  locale: string;
  className?: string;
};

export function OrdersStatusTile({ ordersByStatus, locale, className }: OrdersStatusTileProps) {
  const t = useTranslations("admin.dashboard.orders");
  const empty = isOrdersPipelineEmpty(ordersByStatus);

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} className={className}>
      {empty ? (
        <p className="mb-2 text-xs text-muted" data-testid="orders-empty">
          {t("empty")}
        </p>
      ) : null}
      <ul className="grid grid-cols-2 gap-2 text-sm">
        {STATUS_KEYS.map((status) => (
          <li
            key={status}
            className="flex items-center justify-between gap-2 rounded-md bg-bg px-2 py-1.5"
          >
            <span className="text-muted">{t(`statuses.${status}`)}</span>
            <span className="font-mono font-medium text-text">{ordersByStatus[status]}</span>
          </li>
        ))}
      </ul>
      {!empty ? (
        <a
          href={`/${locale}/orders`}
          className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          {t("openQueue")}
        </a>
      ) : null}
    </TileShell>
  );
}
