"use client";

import type { InputHTMLAttributes } from "react";

export type FieldSize = "sm" | "md" | "lg";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: FieldSize;
  error?: boolean;
}

const sizeClasses: Record<FieldSize, string> = {
  sm: "h-9 min-h-9 px-3 text-sm",
  md: "h-11 min-h-11 px-4 text-body",
  lg: "h-12 min-h-12 px-4 text-body",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Input({
  size = "md",
  error = false,
  className,
  disabled,
  "aria-invalid": ariaInvalid,
  ...rest
}: InputProps) {
  return (
    <input
      disabled={disabled}
      aria-invalid={error ? true : ariaInvalid}
      className={cx(
        "w-full rounded bg-surface font-body text-text",
        "border border-border placeholder:text-text-3",
        "transition-[border-color,box-shadow] duration-fast ease-std",
        "motion-reduce:transition-none",
        "focus-visible:outline-none focus-visible:shadow-focusRing",
        "disabled:cursor-not-allowed disabled:bg-bg-2 disabled:text-text-3",
        error && "border-danger",
        sizeClasses[size],
        className,
      )}
      {...rest}
    />
  );
}
