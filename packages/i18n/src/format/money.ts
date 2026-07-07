export type FormatKOptions = {
  locale?: string;
};

function assertIntegerNgwee(ngwee: number): number {
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

export function formatK(ngwee: number, opts?: FormatKOptions): string {
  const locale = opts?.locale ?? "en-ZM";
  const integerNgwee = assertIntegerNgwee(ngwee);
  return formatMajorUnits(integerNgwee, locale);
}
