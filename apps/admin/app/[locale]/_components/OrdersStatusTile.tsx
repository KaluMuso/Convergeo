"use client";

import { useTranslations } from "next-intl";

import { type OrdersByStatus } from "./api";
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
};

export function OrdersStatusTile({ ordersByStatus }: OrdersStatusTileProps) {
  const t = useTranslations("admin.dashboard.orders");

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")}>
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
    </TileShell>
  );
}
