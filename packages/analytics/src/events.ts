/**
 * Typed analytics event dictionary — the single source of truth for the client
 * mirror's event names and payload shapes. Mirrors the server funnel steps
 * (search -> product_view -> cart -> checkout -> pay). Any money value is an
 * integer number of ngwee (never a float, never a major-unit decimal).
 *
 * Prose reference: `docs/ops/analytics-events.md`.
 */

/** Integer ngwee — the only accepted money representation. */
export type MoneyNgwee = number;

export interface AnalyticsEventMap {
  /** A search query was run. Anonymized: normalized term only, never raw PII. */
  search: {
    normalized_term: string;
    zero_result: boolean;
    result_count?: number;
  };
  /** A product detail page (PDP) was viewed. */
  product_view: {
    product_id: string;
    listing_id?: string;
  };
  /** A listing was added to the cart. */
  cart_add: {
    listing_id: string;
    qty: number;
    unit_price_ngwee: MoneyNgwee;
  };
  /** The checkout flow was entered. */
  checkout_start: {
    checkout_group_id: string;
    total_ngwee: MoneyNgwee;
  };
  /** A payment attempt was initiated. */
  payment_start: {
    checkout_group_id: string;
    method: string;
    total_ngwee: MoneyNgwee;
  };
  /** One or more orders were placed. */
  order_placed: {
    checkout_group_id: string;
    order_count: number;
    total_ngwee: MoneyNgwee;
  };
}

export type AnalyticsEventName = keyof AnalyticsEventMap;
