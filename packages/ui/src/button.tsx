import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  loadingLabel: string;
  children: ReactNode;
}

/** Shared class maps — reused by LinkButton to keep variants in sync. */
export const buttonVariantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-[var(--primary-btn-fg)] hover:bg-[var(--primary-btn-hover)] disabled:bg-text-3 disabled:text-surface",
  secondary:
    "bg-surface text-text border border-border hover:bg-bg-2 disabled:bg-bg-2 disabled:text-text-3",
  ghost: "bg-transparent text-primary hover:bg-primary-tint disabled:text-text-3",
  destructive:
    "bg-danger text-on-danger hover:opacity-90 disabled:bg-text-3 disabled:text-surface disabled:opacity-60",
};

export const buttonSizeClasses: Record<ButtonSize, string> = {
  sm: "h-9 min-h-9 px-3 text-sm gap-2",
  md: "h-11 min-h-11 px-4 text-body gap-2",
  lg: "h-12 min-h-12 px-6 text-body gap-3",
};

export const buttonBaseClasses =
  "inline-flex items-center justify-center rounded font-body font-medium " +
  "transition-[background-color,box-shadow,opacity,transform] duration-fast ease-std " +
  "active:scale-[0.98] motion-reduce:transition-none motion-reduce:active:scale-100 " +
  "focus-visible:outline-none focus-visible:shadow-focusRing " +
  "disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Standard button. No `"use client"` — safe in RSC trees; interactive handlers
 * still work when the parent is a client component.
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  loadingLabel,
  disabled,
  type = "button",
  className,
  children,
  onClick,
  "aria-label": ariaLabel,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      aria-label={loading ? loadingLabel : ariaLabel}
      className={cx(
        buttonBaseClasses,
        buttonVariantClasses[variant],
        buttonSizeClasses[size],
        className,
      )}
      onClick={loading ? undefined : onClick}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
        />
      ) : null}
      <span className={loading ? "opacity-70" : undefined}>{children}</span>
    </button>
  );
}
