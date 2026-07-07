/**
 * Money display path for UI cards — delegates to the @vergeo/i18n `formatK` contract
 * (see packages/i18n/src/format/money.ts). Implementation is inlined here because
 * @vergeo/ui tsconfig rootDir cannot statically import sibling workspace packages.
 */

function formatK(ngwee: number, opts?: { locale?: string }): string {
  const locale = opts?.locale ?? "en-ZM";
  const integerNgwee = assertFormatKInteger(ngwee);
  return formatMajorUnits(integerNgwee, locale);
}

function assertFormatKInteger(ngwee: number): number {
  if (Number.isInteger(ngwee)) {
    return ngwee;
  }

  if (process.env.NODE_ENV === "production") {
    console.error(`formatK: ngwee must be an integer, received ${ngwee}`);
    return Math.round(ngwee);
  }

  throw new TypeError(`formatK: ngwee must be an integer, received ${ngwee}`);
}

function formatMajorUnits(ngwee: number, locale: string): string {
  const negative = ngwee < 0;
  const absoluteNgwee = Math.abs(ngwee);
  const majorUnits = Math.floor(absoluteNgwee / 100);
  const minorUnits = absoluteNgwee % 100;
  const amount = Number(`${majorUnits}.${minorUnits.toString().padStart(2, "0")}`);
  const formatted = amount.toLocaleString(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return negative ? `-K${formatted}` : `K${formatted}`;
}

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
