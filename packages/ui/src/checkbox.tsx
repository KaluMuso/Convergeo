"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

export interface CheckboxProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "size"
> {
  label: ReactNode;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Checkbox({ label, className, disabled, id, ...rest }: CheckboxProps) {
  return (
    <label
      htmlFor={id}
      className={cx(
        "inline-flex min-h-11 cursor-pointer items-center gap-3",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <input
        {...rest}
        id={id}
        type="checkbox"
        disabled={disabled}
        className={cx(
          "size-5 min-h-5 min-w-5 shrink-0 appearance-none rounded-sm border border-border bg-surface",
          "transition-[background-color,border-color,box-shadow] duration-fast ease-std",
          "motion-reduce:transition-none",
          "focus-visible:outline-none focus-visible:shadow-focusRing",
          "checked:border-primary checked:bg-primary",
          "checked:bg-[length:0.75rem_0.75rem] checked:bg-center checked:bg-no-repeat",
          "disabled:cursor-not-allowed",
        )}
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M2.5 6l2.5 2.5 4.5-5' stroke='white' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
        }}
      />
      <span className="font-body text-body text-text">{label}</span>
    </label>
  );
}
