"use client";

import { formatK } from "@vergeo/i18n";

import {
  formatMadeToOrderLeadTime,
  formatListingQuantity,
  formatSaleIncrement,
  resolveMinimumSteps,
  resolveSaleUnit,
  type SaleUnitLabels,
} from "../sale-quantity";

import { QtyStepper, type QtyStepperLabels } from "./qty-stepper";

import type { CartLine, ChangeNotice } from "./mini-cart-drawer";

export type CartLineItemLabels = QtyStepperLabels & {
  unitPrice: string;
  unitPriceMeasured: string;
  saleUnits: SaleUnitLabels;
  madeToOrderLeadTime: string;
  lineTotal: string;
  quotedPriceBadge: string;
  remove: string;
  removeLabel: string;
  saveForLater: string;
  saveForLaterLabel: string;
  outOfStockLine: string;
};

type CartLineItemProps = {
  item: CartLine;
  locale: string;
  notice?: ChangeNotice;
  labels: CartLineItemLabels;
  onQtyChange: (listingId: string, qty: number) => Promise<void>;
  onRemove: (listingId: string) => Promise<void>;
  onSaveForLater?: (listingId: string) => Promise<void>;
};

function isOutOfStock(notice?: ChangeNotice): boolean {
  return notice?.kind === "out_of_stock";
}

export function CartLineItem({
  item,
  locale,
  notice,
  labels,
  onQtyChange,
  onRemove,
  onSaveForLater,
}: CartLineItemProps) {
  const title = item.title_override ?? item.listing_id;
  const outOfStock = isOutOfStock(notice);
  const maxQty = notice?.kind === "qty_reduced" ? (notice.available_qty ?? item.qty) : 99;
  const saleUnit = resolveSaleUnit(item.sale_unit);
  const minimum = resolveMinimumSteps(item.min_steps);
  const formatQuantity = (qty: number) =>
    formatListingQuantity(qty, saleUnit, item.unit_step_milli, locale, labels.saleUnits);
  const unitPriceLabel =
    saleUnit === "each"
      ? labels.unitPrice.replace("{amount}", formatK(item.unit_price_ngwee))
      : labels.unitPriceMeasured
          .replace("{amount}", formatK(item.unit_price_ngwee))
          .replace(
            "{quantity}",
            formatSaleIncrement(saleUnit, item.unit_step_milli, locale, labels.saleUnits),
          );
  const leadTimeLabel = formatMadeToOrderLeadTime(
    item.fulfilment_mode,
    item.lead_time_days,
    labels.madeToOrderLeadTime,
  );

  return (
    <article
      data-testid={`cart-line-${item.listing_id}`}
      className="flex flex-col gap-3 rounded border border-border bg-surface p-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium text-text">{title}</h3>
          <p className="text-sm text-text-2">{unitPriceLabel}</p>
          {leadTimeLabel ? (
            <p
              className="text-xs font-medium text-text-2"
              data-testid={`cart-line-lead-time-${item.listing_id}`}
            >
              {leadTimeLabel}
            </p>
          ) : null}
          {item.is_rfq_quote ? (
            <p className="text-xs font-medium text-primary" data-testid="cart-line-rfq-badge">
              {labels.quotedPriceBadge}
            </p>
          ) : null}
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <QtyStepper
          value={item.qty}
          min={minimum}
          max={outOfStock ? item.qty : maxQty}
          disabled={outOfStock}
          labels={labels}
          formatValue={formatQuantity}
          data-testid={`cart-qty-${item.listing_id}`}
          onChange={(qty) => onQtyChange(item.listing_id, qty)}
        />
        <div className="flex flex-wrap items-center gap-1">
          {onSaveForLater ? (
            <button
              type="button"
              className="min-h-11 px-2 text-sm text-text-2 underline-offset-2 hover:underline"
              aria-label={labels.saveForLaterLabel.replace("{title}", title)}
              data-testid={`cart-save-for-later-${item.listing_id}`}
              onClick={() => void onSaveForLater(item.listing_id)}
            >
              {labels.saveForLater}
            </button>
          ) : null}
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
      </div>
    </article>
  );
}
