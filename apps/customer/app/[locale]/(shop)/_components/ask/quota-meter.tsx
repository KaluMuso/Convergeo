import type { AskQuota } from "./types";

export type QuotaMeterProps = {
  quota: AskQuota;
  /** Resolved, localised "N AI questions left today" label. */
  label: string;
  /** Resolved premium badge text; shown only for the premium tier. */
  premiumLabel?: string | null;
};

/**
 * Compact remaining-quota indicator for Ask Vergeo. Presentational only — the
 * parent resolves ICU plurals so this stays provider-free and trivially testable.
 */
export function QuotaMeter({ quota, label, premiumLabel = null }: QuotaMeterProps) {
  const limit = Math.max(quota.daily_limit, 1);
  const remaining = Math.min(Math.max(quota.remaining, 0), limit);
  const exhausted = remaining === 0;

  return (
    <div
      data-testid="ask-quota-meter"
      data-remaining={remaining}
      data-tier={quota.tier}
      className="flex items-center gap-2 text-xs text-text-3"
    >
      <meter
        min={0}
        max={limit}
        value={remaining}
        aria-label={label}
        className="h-1.5 w-16 overflow-hidden rounded-full"
      />
      <span className={exhausted ? "font-medium text-text-2" : undefined}>{label}</span>
      {quota.tier === "premium" && premiumLabel ? (
        <span className="rounded-full border border-border px-2 py-0.5 text-text-2">
          {premiumLabel}
        </span>
      ) : null}
    </div>
  );
}
