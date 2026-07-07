import { tagTint } from "@vergeo/ui/tokens";

export type PillProps = {
  label: string;
  /** Base hex color for tagTint recipe */
  color: string;
  className?: string;
};

export function Pill({ label, color, className }: PillProps) {
  const tint = tagTint(color);

  return (
    <span
      className={className}
      data-testid="pill"
      style={{
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: "var(--r-pill)",
        fontSize: "var(--fs-sm)",
        fontWeight: 500,
        backgroundColor: tint.bg,
        border: `1px solid ${tint.border}`,
        color: tint.text,
        lineHeight: 1.3,
        maxWidth: "100%",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
