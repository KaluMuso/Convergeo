export type FieldSize = "sm" | "md" | "lg";

/** Shared field chrome for Input, Select, Textarea, SearchField. */
export const fieldSizeClasses: Record<FieldSize, string> = {
  sm: "h-9 min-h-9 px-3 text-sm",
  md: "h-11 min-h-11 px-4 text-body",
  lg: "h-12 min-h-12 px-4 text-body",
};

export const fieldBaseClasses =
  "w-full bg-surface font-body text-text border border-border " +
  "placeholder:text-text-3 " +
  "transition-[border-color,box-shadow,background-color] duration-fast ease-std " +
  "motion-reduce:transition-none " +
  "focus-visible:outline-none focus-visible:border-primary focus-visible:shadow-focusRing " +
  "disabled:cursor-not-allowed disabled:bg-bg-2 disabled:text-text-3 " +
  "aria-[invalid=true]:border-danger";

export const fieldRadiusClass = "rounded";

export function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
