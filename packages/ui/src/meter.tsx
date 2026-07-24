/**
 * Meter — the shared progress/fill primitive (design: SELECTION.md §1.3/§3, the
 * Platform prototype's "KPI cards with progress fills").
 *
 * Extracted from the hand-rolled bars in the vendor profile completeness meter
 * and the admin translations view so dashboards can show a fill instead of a
 * bare number. Presentational and hook-free, so it renders in server or client
 * components alike. `value` is a 0–100 percentage (clamped); `label` is the
 * already-localised accessible name for the progressbar.
 */
export type MeterTone = "primary" | "success" | "warning" | "danger" | "info";

export type MeterProps = {
  /** 0–100. Values outside the range are clamped. */
  value: number;
  /** Already-localised accessible name (aria-label). */
  label: string;
  tone?: MeterTone;
  /** Extra classes for the track (e.g. height/width overrides). */
  className?: string;
};

const fillClasses: Record<MeterTone, string> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Meter({ value, label, tone = "primary", className }: MeterProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      className={cx("h-2 overflow-hidden rounded-full bg-border", className)}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      data-testid="meter"
    >
      <div
        className={cx("h-full rounded-full transition-[width] duration-300", fillClasses[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
