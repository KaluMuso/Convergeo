import type { SelectHTMLAttributes } from "react";

import {
  cx,
  fieldBaseClasses,
  fieldRadiusClass,
  fieldSizeClasses,
  type FieldSize,
} from "./field-styles";

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  size?: FieldSize;
  error?: boolean;
}

/**
 * Native select with token chrome. RSC-safe (no hooks).
 */
export function Select({
  size = "md",
  error = false,
  className,
  disabled,
  children,
  "aria-invalid": ariaInvalid,
  style,
  ...rest
}: SelectProps) {
  return (
    <select
      disabled={disabled}
      aria-invalid={error ? true : ariaInvalid}
      className={cx(
        fieldBaseClasses,
        fieldRadiusClass,
        "appearance-none bg-[length:1rem_1rem] bg-[right_0.75rem_center] bg-no-repeat pr-10",
        fieldSizeClasses[size],
        className,
      )}
      // Inline (not Tailwind classes): app builds don't always generate
      // utilities used only inside packages/ui, which left the chevron tiled
      // across the whole field next to the native arrow.
      style={{
        appearance: "none",
        WebkitAppearance: "none",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 0.75rem center",
        backgroundSize: "1rem 1rem",
        paddingRight: "2.5rem",
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none'%3E%3Cpath d='M4 6l4 4 4-4' stroke='%236B5A3E' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
        ...style,
      }}
      {...rest}
    >
      {children}
    </select>
  );
}
