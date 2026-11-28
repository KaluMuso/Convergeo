import { formatK } from "@vergeo/i18n";

export type PriceTier = {
  /** Inclusive lower bound of the quantity band. */
  minQty: number;
  /** Inclusive upper bound; omitted/null for the open-ended last band. */
  maxQty?: number | null;
  /** Unit price in integer ngwee. */
  unitNgwee: number;
};

export type TierPriceLadderProps = {
  tiers: ReadonlyArray<PriceTier>;
  /** Localised "{min}-{max}" / "{min}+" templates, e.g. "{min}–{max}" and "{min}+". */
  rangeLabel: string;
  openRangeLabel: string;
  /** Heading, e.g. "Buy more, pay less". */
  heading?: string;
  /** Localised per-unit suffix, e.g. "each". */
  unitLabel?: string;
  className?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Quantity-tier ladder (cups sold by 50 / 200 / 1000). Integer ngwee only.
 * Callers must only render it for eligible buyers (D28): this component does no gating.
 */
export function TierPriceLadder({
  tiers,
  rangeLabel,
  openRangeLabel,
  heading,
  unitLabel,
  className,
}: TierPriceLadderProps) {
  const sorted = [...tiers]
    .filter((t) => Number.isInteger(t.unitNgwee) && t.unitNgwee > 0 && t.minQty > 0)
    .sort((a, b) => a.minQty - b.minQty);
  if (sorted.length === 0) return null;
  const base = sorted[0]!.unitNgwee;

  return (
    <div className={cx("flex flex-col gap-1", className)} data-testid="tier-price-ladder">
      {heading ? <p className="m-0 text-sm font-semibold text-text">{heading}</p> : null}
      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(5.5rem,1fr))] gap-1.5 p-0">
        {sorted.map((tier) => {
          const range =
            tier.maxQty != null
              ? rangeLabel
                  .replace("{min}", String(tier.minQty))
                  .replace("{max}", String(tier.maxQty))
              : openRangeLabel.replace("{min}", String(tier.minQty));
          const savePct =
            tier.unitNgwee < base ? Math.round(((base - tier.unitNgwee) * 100) / base) : 0;
          return (
            <li
              key={tier.minQty}
              className="flex flex-col rounded-md border border-border bg-surface px-2 py-1"
              data-testid="tier-price-step"
              data-min-qty={tier.minQty}
            >
              <span className="text-xs text-text-2">{range}</span>
              <span className="v-price text-sm">
                {formatK(tier.unitNgwee)}
                {unitLabel ? (
                  <span className="ml-0.5 text-xs font-normal text-text-2">{unitLabel}</span>
                ) : null}
              </span>
              {savePct > 0 ? (
                <span className="text-xs font-semibold text-discount">−{savePct}%</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
