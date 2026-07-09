"use client";

import { formatK } from "@vergeo/i18n";

import { QtyStepper, type QtyStepperLabels } from "./qty-stepper";

import type { CartLine, ChangeNotice } from "./mini-cart-drawer";

export type CartLineItemLabels = QtyStepperLabels & {
  unitPrice: string;
  lineTotal: string;
  remove: string;
  removeLabel: string;
  outOfStockLine: string;
};

type CartLineItemProps = {
  item: CartLine;
  notice?: ChangeNotice;
  labels: CartLineItemLabels;
  onQtyChange: (listingId: string, qty: number) => Promise<void>;
  onRemove: (listingId: string) => Promise<void>;
};

function isOutOfStock(notice?: ChangeNotice): boolean {
  return notice?.kind === "out_of_stock";
}

export function CartLineItem({ item, notice, labels, onQtyChange, onRemove }: CartLineItemProps) {
  const title = item.title_override ?? item.listing_id;
  const outOfStock = isOutOfStock(notice);
  const maxQty = notice?.kind === "qty_reduced" ? (notice.available_qty ?? item.qty) : 99;

  return (
    <article
      data-testid={`cart-line-${item.listing_id}`}
      className="flex flex-col gap-3 rounded border border-border bg-surface p-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium text-text">{title}</h3>
          <p className="text-sm text-text-2">
            {labels.unitPrice.replace("{amount}", formatK(item.unit_price_ngwee))}
          </p>
          {outOfStock ? (
            <p className="text-sm font-medium text-danger" data-testid="cart-line-oos">
              {labels.outOfStockLine}
            </p>
          ) : null}
        </div>
        <p className="shrink-0 font-mono text-sm font-semibold text-text">
          {labels.lineTotal.replace("{amount}", formatK(item.line_total_ngwee))}
        </p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <QtyStepper
          value={item.qty}
          min={1}
          max={outOfStock ? item.qty : maxQty}
          disabled={outOfStock}
          labels={labels}
          data-testid={`cart-qty-${item.listing_id}`}
          onChange={(qty) => onQtyChange(item.listing_id, qty)}
        />
        <button
          type="button"
          className="min-h-11 px-2 text-sm text-danger"
          aria-label={labels.removeLabel.replace("{title}", title)}
          data-testid={`cart-remove-${item.listing_id}`}
          onClick={() => void onRemove(item.listing_id)}
        >
          {labels.remove}
        </button>
      </div>
    </article>
  );
}
