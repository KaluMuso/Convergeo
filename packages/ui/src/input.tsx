import type { InputHTMLAttributes } from "react";

import {
  cx,
  fieldBaseClasses,
  fieldRadiusClass,
  fieldSizeClasses,
  type FieldSize,
} from "./field-styles";

export type { FieldSize };

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: FieldSize;
  error?: boolean;
}

/**
 * Standard text input. RSC-safe (no hooks).
 */
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
      className={cx(fieldBaseClasses, fieldRadiusClass, fieldSizeClasses[size], className)}
      {...rest}
    />
  );
}
