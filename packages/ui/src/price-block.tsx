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

export function PriceBlock({ ngwee, oldNgwee, savingsLabel, className }: PriceBlockProps) {
  const priceNgwee = assertIntegerNgwee(ngwee, "ngwee");
  const formattedPrice = formatK(priceNgwee);

  const hasOldPrice =
    oldNgwee !== undefined && assertIntegerNgwee(oldNgwee, "oldNgwee") > priceNgwee;
  const formattedOldPrice = hasOldPrice ? formatK(oldNgwee) : undefined;

  return (
    <div className={className} data-testid="price-block">
      <span
        className="font-mono text-price font-bold text-text"
        style={{ fontSize: "var(--fs-price)" }}
      >
        {formattedPrice}
      </span>
      {formattedOldPrice ? (
        <span
          className="ml-2 font-mono text-sm line-through"
          style={{ color: "var(--text-3)", textDecoration: "line-through" }}
        >
          {formattedOldPrice}
        </span>
      ) : null}
      {hasOldPrice && savingsLabel ? (
        <span
          className="ml-2 inline-block rounded-pill px-2 py-0.5 text-micro font-semibold uppercase tracking-wide"
          style={{
            color: "var(--accent)",
            backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)",
          }}
          data-testid="price-savings"
        >
          {savingsLabel}
        </span>
      ) : null}
    </div>
  );
}
