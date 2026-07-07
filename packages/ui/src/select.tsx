"use client";

import type { SelectHTMLAttributes } from "react";

import type { FieldSize } from "./input";

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
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

export function Select({
  size = "md",
  error = false,
  className,
  disabled,
  children,
  "aria-invalid": ariaInvalid,
  ...rest
}: SelectProps) {
  return (
    <select
      disabled={disabled}
      aria-invalid={error ? true : ariaInvalid}
      className={cx(
        "w-full appearance-none rounded bg-surface font-body text-text",
        "border border-border",
        "bg-[length:1rem_1rem] bg-[right_0.75rem_center] bg-no-repeat",
        "transition-[border-color,box-shadow] duration-fast ease-std",
        "motion-reduce:transition-none",
        "focus-visible:outline-none focus-visible:shadow-focusRing",
        "disabled:cursor-not-allowed disabled:bg-bg-2 disabled:text-text-3",
        error && "border-danger",
        sizeClasses[size],
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none'%3E%3Cpath d='M4 6l4 4 4-4' stroke='%236B5A3E' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
      }}
      {...rest}
    >
      {children}
    </select>
  );
}
