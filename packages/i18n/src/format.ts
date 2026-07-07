export type FormatKOptions = {
  locale?: string;
};

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
  return formatMajorUnits(ngwee, locale);
}

export function formatDate(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}
