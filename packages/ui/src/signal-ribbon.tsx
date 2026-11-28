export type SignalRibbonKind = "preferred" | "verified_business" | "verified_id";

export type SignalRibbonProps = {
  kind: SignalRibbonKind;
  label: string;
  className?: string;
};

const kindClasses: Record<SignalRibbonKind, string> = {
  preferred: "bg-accent-tint border-accent/60",
  verified_business: "bg-surface border-success/60",
  verified_id: "bg-surface border-info/60",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * One trust ribbon per card. Sits flush on the media edge (positioned by the
 * parent); the label stays on `text-text` so contrast holds on every tint.
 */
export function SignalRibbon({ kind, label, className }: SignalRibbonProps) {
  return (
    <span
      className={cx(
        "inline-flex max-w-full items-center rounded-tr-md border-r border-t px-2 py-0.5 text-micro font-semibold leading-snug text-text",
        kindClasses[kind],
        className,
      )}
      data-testid="signal-ribbon"
      data-kind={kind}
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
