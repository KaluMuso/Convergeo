"use client";

import { useTheme } from "./theme-provider";

import type { ThemeChoice } from "./theme-script";

export type ThemePreferenceProps = {
  /** Group legend, e.g. "Display". */
  label: string;
  /** Optional help text under the legend. */
  description?: string;
  lightLabel: string;
  darkLabel: string;
  systemLabel: string;
  className?: string;
};

const OPTIONS: readonly ThemeChoice[] = ["system", "light", "dark"];

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Explicit light / dark / system radios for Account → Preferences.
 * Default choice is `system` (ThemeProvider + ThemeScript). Applies immediately
 * via localStorage — no server round-trip.
 */
export function ThemePreference({
  label,
  description,
  lightLabel,
  darkLabel,
  systemLabel,
  className,
}: ThemePreferenceProps) {
  const { theme, setTheme } = useTheme();
  const labels: Record<ThemeChoice, string> = {
    light: lightLabel,
    dark: darkLabel,
    system: systemLabel,
  };

  return (
    <fieldset
      className={cx("space-y-3 rounded border border-border bg-surface p-4", className)}
      data-testid="theme-preference"
    >
      <legend className="px-1 font-medium text-text">{label}</legend>
      {description ? <p className="text-sm text-text-2">{description}</p> : null}
      <div role="radiogroup" aria-label={label} className="flex flex-col gap-2">
        {OPTIONS.map((choice) => {
          const id = `theme-pref-${choice}`;
          const checked = theme === choice;
          return (
            <label
              key={choice}
              htmlFor={id}
              className={cx(
                "flex min-h-11 cursor-pointer items-center gap-3 rounded px-3",
                "border border-transparent transition-colors duration-fast ease-std",
                "motion-reduce:transition-none",
                "hover:bg-bg-2 focus-within:shadow-focusRing",
                checked && "border-primary bg-primary-tint",
              )}
            >
              <input
                id={id}
                type="radio"
                name="theme-preference"
                value={choice}
                checked={checked}
                onChange={() => setTheme(choice)}
                className="size-4 accent-[var(--primary)]"
              />
              <span className="text-body text-text">{labels[choice]}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
