"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size"> {
  label: ReactNode;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Radio({ label, className, disabled, id, ...rest }: RadioProps) {
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
        type="radio"
        disabled={disabled}
        className={cx(
          "size-5 min-h-5 min-w-5 shrink-0 appearance-none rounded-full border border-border bg-surface",
          "transition-[background-color,border-color,box-shadow] duration-fast ease-std",
          "motion-reduce:transition-none",
          "focus-visible:outline-none focus-visible:shadow-focusRing",
          "checked:border-primary checked:bg-primary",
          "checked:shadow-[inset_0_0_0_3px_var(--surface)]",
          "disabled:cursor-not-allowed",
        )}
      />
      <span className="font-body text-body text-text">{label}</span>
    </label>
  );
}
