import type { TextareaHTMLAttributes } from "react";

import { cx, fieldBaseClasses, fieldRadiusClass, type FieldSize } from "./field-styles";

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "size"> {
  size?: FieldSize;
  error?: boolean;
}

const sizeClasses: Record<FieldSize, string> = {
  sm: "min-h-[4.5rem] px-3 py-2 text-sm",
  md: "min-h-[5.5rem] px-4 py-3 text-body",
  lg: "min-h-[6.5rem] px-4 py-3 text-body",
};

/**
 * Standard textarea. RSC-safe (no hooks).
 */
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
      className={cx(fieldBaseClasses, fieldRadiusClass, "resize-y", sizeClasses[size], className)}
      {...rest}
    />
  );
}
