"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

export interface SwitchProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "role" | "size"
> {
  label: ReactNode;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Switch({
  label,
  className,
  disabled,
  id,
  checked,
  defaultChecked,
  onChange,
  ...rest
}: SwitchProps) {
  return (
    <label
      htmlFor={id}
      className={cx(
        "inline-flex min-h-11 cursor-pointer items-center gap-3",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span className="relative inline-flex shrink-0 items-center">
        <input
          {...rest}
          id={id}
          type="checkbox"
          role="switch"
          disabled={disabled}
          checked={checked}
          defaultChecked={defaultChecked}
          onChange={onChange}
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className={cx(
            "block h-7 w-12 rounded-pill border border-border bg-bg-2",
            "transition-[background-color,border-color] duration-fast ease-std",
            "motion-reduce:transition-none",
            "peer-focus-visible:shadow-focusRing",
            "peer-checked:border-primary peer-checked:bg-primary",
            "peer-disabled:cursor-not-allowed",
          )}
        />
        <span
          aria-hidden="true"
          className={cx(
            "pointer-events-none absolute left-0.5 top-0.5 size-6 rounded-pill bg-surface shadow-1",
            "transition-transform duration-fast ease-std",
            "motion-reduce:transition-none",
            "peer-checked:translate-x-5",
          )}
        />
      </span>
      <span className="font-body text-body text-text">{label}</span>
    </label>
  );
}
