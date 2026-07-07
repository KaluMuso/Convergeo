"use client";

import type { TextareaHTMLAttributes } from "react";

import type { FieldSize } from "./input";

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "size"> {
  size?: FieldSize;
  error?: boolean;
}

const sizeClasses: Record<FieldSize, string> = {
  sm: "min-h-[4.5rem] px-3 py-2 text-sm",
  md: "min-h-[5.5rem] px-4 py-3 text-body",
  lg: "min-h-[6.5rem] px-4 py-3 text-body",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Textarea({
  size = "md",
  error = false,
  className,
  disabled,
  "aria-invalid": ariaInvalid,
  ...rest
}: TextareaProps) {
  return (
    <textarea
      disabled={disabled}
      aria-invalid={error ? true : ariaInvalid}
      className={cx(
        "w-full resize-y rounded bg-surface font-body text-text",
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
