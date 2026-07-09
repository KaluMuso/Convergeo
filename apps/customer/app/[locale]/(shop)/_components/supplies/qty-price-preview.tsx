import { formatK } from "@vergeo/i18n";

export type PriceTier = {
  minQty: number;
  ngwee: number;
};

export type ApiPriceTier = {
  min_qty: number;
  price_ngwee: number;
};

export function normalizeTiers(
  priceTiers: ApiPriceTier[] | null | undefined,
  basePriceNgwee: number,
): PriceTier[] {
  if (priceTiers && priceTiers.length > 0) {
    return priceTiers.map((tier) => ({
      minQty: tier.min_qty,
      ngwee: tier.price_ngwee,
    }));
  }
  return [{ minQty: 1, ngwee: basePriceNgwee }];
}

export function selectUnitPriceNgwee(
  basePriceNgwee: number,
  wholesale: boolean,
  qty: number,
  tiers: PriceTier[],
): number {
  if (wholesale && tiers.length > 0) {
    const applicable = tiers.filter((tier) => qty >= tier.minQty);
    if (applicable.length > 0) {
      return applicable.reduce((best, tier) => (tier.minQty > best.minQty ? tier : best)).ngwee;
    }
  }
  return basePriceNgwee;
}

export function lineTotalNgwee(qty: number, unitPriceNgwee: number): number {
  return qty * unitPriceNgwee;
}

export type QtyPricePreviewProps = {
  qty: number;
  unitPriceNgwee: number;
  lineTemplate: string;
};

export function QtyPricePreview({ qty, unitPriceNgwee, lineTemplate }: QtyPricePreviewProps) {
  const totalNgwee = lineTotalNgwee(qty, unitPriceNgwee);

  const line = lineTemplate
    .replace("{qty}", String(qty))
    .replace("{unitPrice}", formatK(unitPriceNgwee))
    .replace("{total}", formatK(totalNgwee));

  return (
    <p
      className="font-mono text-sm text-text"
      data-testid="supplies-qty-preview"
      aria-live="polite"
    >
      {line}
    </p>
  );
}
