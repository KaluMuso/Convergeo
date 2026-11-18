import { formatK } from "@vergeo/i18n";

export type ExtraPricing = "fixed" | "range" | "pay_as_you_go";
export type ExtraUnit = "one_off" | "per_month" | "per_item";
export type ExtraRequestStatus =
  "requested" | "quoted" | "approved" | "fulfilled" | "cancelled";

export type Extra = {
  key: string;
  name: string;
  description: string;
  pricing: ExtraPricing;
  price_ngwee: number | null;
  price_max_ngwee: number | null;
  unit: ExtraUnit;
  price_is_placeholder: boolean;
};

export type ExtraRequest = {
  id: string;
  extra_key: string;
  quantity: number;
  note: string | null;
  status: ExtraRequestStatus;
  quoted_price_ngwee: number | null;
  admin_note: string | null;
  created_at: string | null;
};

export type ExtrasCatalogueResponse = {
  extras: Extra[];
  requests: ExtraRequest[];
};

export const OPEN_REQUEST_STATUSES: ReadonlySet<ExtraRequestStatus> = new Set([
  "requested",
  "quoted",
  "approved",
]);

type Translate = (
  key: string,
  values?: Record<string, string | number>,
) => string;

/** "K500.00 – K5,000.00 one-off", "From K10.00 per item", "K75.00 / month". */
export function extraPriceLabel(extra: Extra, t: Translate): string {
  const unit = t(`unit.${extra.unit}`);
  if (
    extra.pricing === "range" &&
    extra.price_ngwee !== null &&
    extra.price_max_ngwee !== null
  ) {
    return t("price.range", {
      min: formatK(extra.price_ngwee),
      max: formatK(extra.price_max_ngwee),
      unit,
    });
  }
  if (extra.pricing === "pay_as_you_go") {
    return extra.price_ngwee !== null
      ? t("price.paygFrom", { price: formatK(extra.price_ngwee), unit })
      : t("price.payg");
  }
  if (extra.price_ngwee !== null) {
    return t("price.fixed", { price: formatK(extra.price_ngwee), unit });
  }
  return t("price.onRequest");
}

/** The open request (if any) for an extra: one open request per shop and extra. */
export function openRequestFor(
  requests: ExtraRequest[],
  key: string,
): ExtraRequest | undefined {
  return requests.find(
    (r) => r.extra_key === key && OPEN_REQUEST_STATUSES.has(r.status),
  );
}
