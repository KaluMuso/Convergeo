import type { InputHTMLAttributes, ReactNode } from "react";

import { cx, fieldBaseClasses, fieldSizeClasses, type FieldSize } from "./field-styles";

export type SearchFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "type"> & {
  size?: FieldSize;
  error?: boolean;
  /** Optional leading icon (decorative; field uses type=search). */
  leadingIcon?: ReactNode;
  /** Optional trailing control (e.g. submit button). */
  trailing?: ReactNode;
};

/**
 * Search-shaped field — pill radius per audit (filters/search, not solid CTAs).
 * RSC-safe.
 */
export function SearchField({
  size = "md",
  error = false,
  className,
  disabled,
  leadingIcon,
  trailing,
  "aria-invalid": ariaInvalid,
  ...rest
}: SearchFieldProps) {
  return (
    <div
      className={cx(
        "flex w-full items-center gap-2 rounded-pill border border-border bg-surface",
        "transition-[border-color,box-shadow] duration-fast ease-std motion-reduce:transition-none",
        "focus-within:border-primary focus-within:shadow-focusRing",
        error && "border-danger",
        disabled && "cursor-not-allowed bg-bg-2 opacity-60",
        className,
      )}
      data-testid="search-field"
    >
      {leadingIcon ? (
        <span className="pl-4 text-text-2" aria-hidden>
          {leadingIcon}
        </span>
      ) : null}
      <input
        type="search"
        disabled={disabled}
        aria-invalid={error ? true : ariaInvalid}
        className={cx(
          fieldBaseClasses,
          "min-w-0 flex-1 rounded-pill border-0 bg-transparent shadow-none focus-visible:shadow-none",
          fieldSizeClasses[size],
          leadingIcon ? "pl-0" : undefined,
          trailing ? "pr-0" : undefined,
        )}
        {...rest}
      />
      {trailing ? <div className="pr-2">{trailing}</div> : null}
    </div>
  );
}
