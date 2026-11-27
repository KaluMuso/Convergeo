export type SignalBadgeKind =
  "cheapest" | "near_you" | "made_in_zambia" | "top_rated" | "fast_delivery" | "low_stock" | "new";

export type SignalBadgeProps = {
  kind: SignalBadgeKind;
  /** Localised label; the parent owns the copy (RSC-safe, no i18n import here). */
  label: string;
  className?: string;
};

/** Token classes only. Never red: red is reserved for sold out and discounts. */
const kindClasses: Record<SignalBadgeKind, string> = {
  cheapest: "bg-primary-tint text-primary border-primary/30",
  near_you: "bg-surface text-text border-border",
  made_in_zambia: "bg-surface text-text border-success/50",
  top_rated: "bg-surface text-text border-accent/50",
  fast_delivery: "bg-surface text-text border-info/50",
  low_stock: "bg-surface text-text border-warning/60",
  new: "bg-surface text-text border-primary/40",
};

const dotClasses: Record<SignalBadgeKind, string> = {
  cheapest: "bg-primary",
  near_you: "bg-info",
  made_in_zambia: "bg-success",
  top_rated: "bg-accent",
  fast_delivery: "bg-info",
  low_stock: "bg-warning",
  new: "bg-primary",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function SignalBadge({ kind, label, className }: SignalBadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex max-w-full items-center gap-1 rounded-pill border px-2 py-0.5 text-micro font-semibold leading-snug",
        kindClasses[kind],
        className,
      )}
      data-testid={`signal-badge-${kind}`}
      data-kind={kind}
    >
      <span
        aria-hidden="true"
        className={cx("h-1.5 w-1.5 shrink-0 rounded-full", dotClasses[kind])}
      />
      <span className="truncate">{label}</span>
    </span>
  );
}

export type SignalBadgeRowProps = {
  badges: ReadonlyArray<{ kind: SignalBadgeKind; label: string }>;
  /** Hard cap from the spec (docs/plan/product-signals.md): 2 per card. */
  max?: number;
  className?: string;
};

export function SignalBadgeRow({ badges, max = 2, className }: SignalBadgeRowProps) {
  const visible = badges.slice(0, max);
  if (visible.length === 0) return null;
  return (
    <div
      className={cx("flex flex-wrap items-center gap-1", className)}
      data-testid="signal-badge-row"
    >
      {visible.map((badge) => (
        <SignalBadge key={badge.kind} kind={badge.kind} label={badge.label} />
      ))}
    </div>
  );
}
