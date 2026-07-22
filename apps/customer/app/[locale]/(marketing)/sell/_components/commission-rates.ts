/**
 * D4 commission rates — typed fallback mirror of `commission_rates` seed in
 * `0008_config.sql`. Live values are fetched server-side from
 * `GET /public/config/commission-rates`; this constant is used only when that
 * request fails so the Sell page never crashes on a transient API outage.
 */
import { formatNumber } from "@vergeo/i18n";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

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

type CommissionRatesApiResponse = {
  rates: { category_key: string; rate_pct: number }[];
  updated_at: string;
};

function mergeLiveCommissionRates(
  liveRates: CommissionRatesApiResponse["rates"],
): CommissionRate[] {
  const liveByKey = new Map(liveRates.map((rate) => [rate.category_key, rate.rate_pct] as const));

  return COMMISSION_RATES.map((fallback) => ({
    categoryKey: fallback.categoryKey,
    ratePct: liveByKey.get(fallback.categoryKey) ?? fallback.ratePct,
  }));
}

/** Fetch live D4 commission rates; fall back to the static seed on any failure. */
export async function fetchCommissionRates(): Promise<CommissionRate[]> {
  const url = absoluteApiUrl("/public/config/commission-rates");
  if (!url) {
    return [...COMMISSION_RATES];
  }

  try {
    const response = await fetch(url, { next: { revalidate: 300 } });
    if (!response.ok) {
      return [...COMMISSION_RATES];
    }

    const data = (await response.json()) as CommissionRatesApiResponse;
    if (!Array.isArray(data.rates) || data.rates.length === 0) {
      return [...COMMISSION_RATES];
    }

    return mergeLiveCommissionRates(data.rates);
  } catch {
    return [...COMMISSION_RATES];
  }
}

export function formatCommissionRateLabel(
  ratePct: number,
  locale: string,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  const formattedRate = formatNumber(ratePct, locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  });

  return t("commission.rate", { rate: formattedRate });
}

export function buildCommissionTableRows(
  rates: readonly CommissionRate[],
  locale: string,
  getCategoryLabel: (categoryKey: string) => string,
  t: (key: string, values?: Record<string, string | number>) => string,
): CommissionTableRow[] {
  return rates.map((rate) => ({
    categoryKey: rate.categoryKey,
    label: getCategoryLabel(rate.categoryKey),
    rateLabel: formatCommissionRateLabel(rate.ratePct, locale, t),
  }));
}
