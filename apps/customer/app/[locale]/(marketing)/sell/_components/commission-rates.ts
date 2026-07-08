/**
 * D4 commission rates — mirrors `commission_rates` seed in `0008_config.sql`.
 *
 * TODO(config): Bind to live `commission_rates` via public config read once
 * M13-P07 / catalog config endpoint lands (replace this constant module).
 */
export type CommissionRate = {
  categoryKey: string;
  ratePct: number;
};

export const COMMISSION_RATES: readonly CommissionRate[] = [
  { categoryKey: "electronics", ratePct: 5 },
  { categoryKey: "home", ratePct: 8 },
  { categoryKey: "fashion_beauty", ratePct: 10 },
  { categoryKey: "services", ratePct: 12 },
  { categoryKey: "event_tickets", ratePct: 5 },
  { categoryKey: "supplies", ratePct: 3 },
  { categoryKey: "groceries", ratePct: 5 },
  { categoryKey: "default", ratePct: 8 },
  { categoryKey: "free_events", ratePct: 0 },
] as const;

export type CommissionTableRow = {
  categoryKey: string;
  label: string;
  rateLabel: string;
};

export function buildCommissionTableRows(
  rates: readonly CommissionRate[],
  getCategoryLabel: (categoryKey: string) => string,
  formatRate: (ratePct: number) => string,
): CommissionTableRow[] {
  return rates.map((rate) => ({
    categoryKey: rate.categoryKey,
    label: getCategoryLabel(rate.categoryKey),
    rateLabel: formatRate(rate.ratePct),
  }));
}
