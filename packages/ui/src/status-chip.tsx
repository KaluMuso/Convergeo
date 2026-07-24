/**
 * StatusChip — the shared "soft status chip" primitive (design: SELECTION.md §3
 * "status chips: green/amber/red bg + deep text").
 *
 * Consolidates the `border-<tone> bg-<tone>/10 text-<tone>` recipe that admin
 * surfaces had been re-implementing per feature (SLA badges, repeat-offender,
 * inline order/dispute chips). Tone is the only visual axis; the label is
 * caller-provided and MUST already be localised. Colours are token utilities so
 * dark mode remaps automatically.
 */
export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

export type StatusChipProps = {
  tone: StatusTone;
  /** Already-localised text. */
  label: string;
  className?: string;
};

const toneClasses: Record<StatusTone, string> = {
  success: "border-success bg-success/10 text-success",
  warning: "border-warning bg-warning/10 text-warning",
  danger: "border-danger bg-danger/10 text-danger",
  info: "border-info bg-info/10 text-info",
  neutral: "border-border bg-bg-2 text-text-2",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function StatusChip({ tone, label, className }: StatusChipProps) {
  return (
    <span
      className={cx(
        "inline-flex min-h-6 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium leading-snug",
        toneClasses[tone],
        className,
      )}
      data-testid={`status-chip-${tone}`}
      data-tone={tone}
    >
      {label}
    </span>
  );
}

/**
 * Order-lifecycle vocabulary → tone. Amber = needs vendor action, blue =
 * in-flight, green = terminal-good, red = cancelled. Shared by the vendor order
 * queue and the admin order search so both read the same traffic-light. Unknown
 * statuses degrade to neutral rather than throwing.
 */
const ORDER_STATUS_TONE: Record<string, StatusTone> = {
  placed: "warning",
  confirmed: "info",
  processing: "info",
  ready: "info",
  shipped: "info",
  delivered: "success",
  completed: "success",
  cancelled: "danger",
};

export function orderStatusTone(status: string): StatusTone {
  return ORDER_STATUS_TONE[status] ?? "neutral";
}
