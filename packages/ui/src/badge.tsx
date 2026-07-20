export type BadgeVariant =
  | "sold_out"
  | "promotion"
  | "public"
  | "selling_fast"
  | "free"
  | "new"
  | "featured"
  | "sale"
  | "in_stock"
  | "out_of_stock"
  | "sponsored"
  | "sample";

export type BadgeProps = {
  variant: BadgeVariant;
  label: string;
  className?: string;
};

/**
 * Token-driven badge colours via CSS variables so dark mode remaps correctly.
 * Avoids baking light-mode hex from tokens.ts into inline styles.
 */
const variantTokenClasses: Record<BadgeVariant, string> = {
  sold_out: "bg-danger text-on-danger",
  promotion: "bg-accent text-surface",
  public: "bg-info text-surface",
  selling_fast: "bg-warning text-text",
  free: "bg-success text-surface",
  new: "bg-primary text-[var(--primary-btn-fg)]",
  featured: "bg-primary-deep text-surface",
  sale: "bg-discount text-on-danger",
  in_stock: "bg-success text-surface",
  out_of_stock: "bg-danger text-on-danger",
  sponsored: "bg-primary-tint text-primary",
  sample: "bg-warning text-text",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Badge({ variant, label, className }: BadgeProps) {
  return (
    <span
      className={cx(
        "inline-block rounded-pill px-2.5 py-0.5 text-micro font-semibold uppercase tracking-wide leading-snug",
        variantTokenClasses[variant],
        className,
      )}
      data-testid={`badge-${variant}`}
      data-variant={variant}
    >
      {label}
    </span>
  );
}
