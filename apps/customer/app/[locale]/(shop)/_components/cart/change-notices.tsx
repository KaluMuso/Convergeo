"use client";

import { formatK } from "@vergeo/i18n";

import type { ChangeNotice } from "./mini-cart-drawer";

export type ChangeNoticeLabels = {
  title: string;
  priceChanged: string;
  outOfStock: string;
  qtyReduced: string;
};

type ChangeNoticesProps = {
  notices: ChangeNotice[];
  labels: ChangeNoticeLabels;
  titleByListingId?: Record<string, string>;
};

function noticeMessage(notice: ChangeNotice, labels: ChangeNoticeLabels, title?: string): string {
  const itemLabel = title ?? notice.listing_id;

  switch (notice.kind) {
    case "price_changed":
      return labels.priceChanged
        .replace("{oldPrice}", formatK(notice.snapshot_price_ngwee))
        .replace(
          "{newPrice}",
          notice.current_price_ngwee !== null ? formatK(notice.current_price_ngwee) : "—",
        )
        .concat(title ? ` (${itemLabel})` : "");
    case "out_of_stock":
      return labels.outOfStock.concat(title ? ` (${itemLabel})` : "");
    case "qty_reduced":
      return labels.qtyReduced
        .replace("{available}", String(notice.available_qty ?? 0))
        .replace("{requested}", String(notice.requested_qty))
        .concat(title ? ` (${itemLabel})` : "");
    default:
      return itemLabel;
  }
}

export function ChangeNotices({ notices, labels, titleByListingId }: ChangeNoticesProps) {
  if (notices.length === 0) {
    return null;
  }

  return (
    <section
      aria-live="polite"
      data-testid="cart-change-notices"
      className="flex flex-col gap-2 rounded border border-warning/40 bg-warning/10 p-3"
    >
      <h2 className="text-sm font-semibold text-text">{labels.title}</h2>
      <ul className="flex flex-col gap-2">
        {notices.map((notice) => (
          <li
            key={`${notice.listing_id}-${notice.kind}`}
            data-testid={`cart-notice-${notice.kind}-${notice.listing_id}`}
            className="text-sm text-text-2"
          >
            {noticeMessage(notice, labels, titleByListingId?.[notice.listing_id])}
          </li>
        ))}
      </ul>
    </section>
  );
}
