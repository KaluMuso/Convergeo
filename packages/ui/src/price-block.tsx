import { formatK } from "@vergeo/i18n";

export type PriceBlockProps = {
  ngwee: number;
  oldNgwee?: number;
  /** Localized savings chip copy, e.g. "Save K50.00" */
  savingsLabel?: string;
  className?: string;
};

function assertIntegerNgwee(value: number, field: string): number {
  if (!Number.isInteger(value)) {
    if (process.env.NODE_ENV === "production") {
      console.error(`PriceBlock: ${field} must be an integer ngwee, received ${value}`);
      return Math.round(value);
    }
    throw new TypeError(`PriceBlock: ${field} must be an integer ngwee, received ${value}`);
  }
  return value;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Product price + optional struck old price and savings chip.
 * Uses semantic `--price` / `--discount` tokens.
 */
export function PriceBlock({ ngwee, oldNgwee, savingsLabel, className }: PriceBlockProps) {
  const priceNgwee = assertIntegerNgwee(ngwee, "ngwee");
  const formattedPrice = formatK(priceNgwee);

  const hasOldPrice =
    oldNgwee !== undefined && assertIntegerNgwee(oldNgwee, "oldNgwee") > priceNgwee;
  const formattedOldPrice = hasOldPrice ? formatK(oldNgwee) : undefined;

  return (
    <div className={cx("flex flex-wrap items-baseline gap-2", className)} data-testid="price-block">
      <span className="font-mono text-price font-bold text-[var(--price)]">{formattedPrice}</span>
      {formattedOldPrice ? (
        <span className="font-mono text-sm text-text-3 line-through">{formattedOldPrice}</span>
      ) : null}
      {hasOldPrice && savingsLabel ? (
        <span
          className="inline-block rounded-pill bg-[color-mix(in_srgb,var(--discount)_12%,transparent)] px-2 py-0.5 text-micro font-semibold uppercase tracking-wide text-discount"
          data-testid="price-savings"
        >
          {savingsLabel}
        </span>
      ) : null}
    </div>
  );
}
