import type { ReactNode } from "react";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export type FilterBoxProps = {
  title: string;
  children: ReactNode;
  className?: string;
};

/** A titled card holding one filter group (chips or toggles). */
export function FilterBox({ title, children, className }: FilterBoxProps) {
  return (
    <fieldset
      className={cx(
        "m-0 flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-3",
        className,
      )}
      data-testid="filter-box"
    >
      <legend className="float-left mb-0 w-full p-0 text-sm font-semibold text-text">
        {title}
      </legend>
      <div className="clear-both flex flex-wrap gap-1.5">{children}</div>
    </fieldset>
  );
}

export type FilterChipProps = {
  label: string;
  selected: boolean;
  /** Result count for this chip; hidden when undefined. */
  count?: number;
  /** Link target; the chip is a real anchor so filters work without JS and are URL-synced. */
  href: string;
  /** Render as a non-interactive chip when the facet is empty. */
  disabled?: boolean;
  onNavigate?: (href: string) => void;
  className?: string;
};

export function FilterChip({
  label,
  selected,
  count,
  href,
  disabled = false,
  onNavigate,
  className,
}: FilterChipProps) {
  const body = (
    <>
      <span>{label}</span>
      {count !== undefined ? (
        <span className="text-xs text-text-2" data-testid="filter-chip-count">
          {count}
        </span>
      ) : null}
    </>
  );
  const classes = cx(
    "inline-flex min-h-11 items-center gap-1.5 rounded-pill border px-3 text-sm font-medium",
    selected ? "border-primary bg-primary-tint text-primary" : "border-border bg-surface text-text",
    disabled && "pointer-events-none opacity-50",
    className,
  );
  if (disabled && !selected) {
    return (
      <span className={classes} data-testid="filter-chip" aria-disabled="true">
        {body}
      </span>
    );
  }
  return (
    <a
      href={href}
      className={classes}
      data-testid="filter-chip"
      data-selected={selected ? "true" : "false"}
      aria-pressed={selected}
      onClick={
        onNavigate
          ? (event) => {
              event.preventDefault();
              onNavigate(href);
            }
          : undefined
      }
    >
      {body}
    </a>
  );
}
