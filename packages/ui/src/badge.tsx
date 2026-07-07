import { tokens } from "@vergeo/ui/tokens";

export type BadgeVariant =
  "sold_out" | "promotion" | "public" | "selling_fast" | "free" | "new" | "featured";

export type BadgeProps = {
  variant: BadgeVariant;
  label: string;
  className?: string;
};

const variantColors: Record<BadgeVariant, { bg: string; text: string }> = {
  sold_out: { bg: tokens.colors.danger, text: tokens.colors.surface },
  promotion: { bg: tokens.colors.accent, text: tokens.colors.surface },
  public: { bg: tokens.colors.info, text: tokens.colors.surface },
  selling_fast: { bg: tokens.colors.warning, text: tokens.colors.text },
  free: { bg: tokens.colors.success, text: tokens.colors.surface },
  new: { bg: tokens.colors.primary, text: tokens.colors.surface },
  featured: { bg: tokens.colors.primaryDeep, text: tokens.colors.surface },
};

export function Badge({ variant, label, className }: BadgeProps) {
  const colors = variantColors[variant];

  return (
    <span
      className={className}
      data-testid={`badge-${variant}`}
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: "var(--r-pill)",
        fontSize: "var(--fs-micro)",
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        backgroundColor: colors.bg,
        color: colors.text,
        lineHeight: 1.4,
      }}
    >
      {label}
    </span>
  );
}
