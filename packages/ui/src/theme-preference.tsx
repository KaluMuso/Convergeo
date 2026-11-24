"use client";

import {
  ACCENT_CHOICES,
  MONO_LIGHT,
  GREEN_LIGHT,
  BLUE_LIGHT,
  GOLD_LIGHT,
  type AccentChoice,
} from "./accent-palette";
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
  /** Accent row legend (defaults to "Accent colour"). */
  accentLabel?: string;
  accentMonoLabel?: string;
  accentGreenLabel?: string;
  accentBlueLabel?: string;
  accentGoldLabel?: string;
  className?: string;
};

const THEME_OPTIONS: readonly ThemeChoice[] = ["system", "light", "dark"];

const ACCENT_SWATCH: Record<AccentChoice, string> = {
  mono: MONO_LIGHT.primary,
  green: GREEN_LIGHT.primary,
  blue: BLUE_LIGHT.primary,
  gold: GOLD_LIGHT.primary,
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Light / dark / system radios plus accent swatches for Preferences screens.
 */
export function ThemePreference({
  label,
  description,
  lightLabel,
  darkLabel,
  systemLabel,
  accentLabel = "Accent colour",
  accentMonoLabel = "Mono",
  accentGreenLabel = "Green",
  accentBlueLabel = "Blue",
  accentGoldLabel = "Gold",
  className,
}: ThemePreferenceProps) {
  const { theme, setTheme, accent, setAccent } = useTheme();
  const labels: Record<ThemeChoice, string> = {
    light: lightLabel,
    dark: darkLabel,
    system: systemLabel,
  };
  const accentLabels: Record<AccentChoice, string> = {
    mono: accentMonoLabel,
    green: accentGreenLabel,
    blue: accentBlueLabel,
    gold: accentGoldLabel,
  };

  return (
    <fieldset
      className={cx("space-y-4 rounded border border-border bg-surface p-4", className)}
      data-testid="theme-preference"
    >
      <legend className="px-1 font-medium text-text">{label}</legend>
      {description ? <p className="text-sm text-text-2">{description}</p> : null}
      <div role="radiogroup" aria-label={label} className="flex flex-col gap-2">
        {THEME_OPTIONS.map((choice) => {
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

      <div className="border-t border-border pt-4">
        <p className="mb-2 text-sm font-medium text-text">{accentLabel}</p>
        <div
          role="radiogroup"
          aria-label={accentLabel}
          className="flex flex-wrap gap-2"
          data-testid="accent-preference"
        >
          {ACCENT_CHOICES.map((choice) => {
            const id = `accent-pref-${choice}`;
            const checked = accent === choice;
            return (
              <label
                key={choice}
                htmlFor={id}
                className={cx(
                  "flex cursor-pointer flex-col items-center gap-1 rounded-lg border px-3 py-2",
                  "transition-colors duration-fast ease-std motion-reduce:transition-none",
                  checked ? "border-primary bg-primary-tint" : "border-border hover:bg-bg-2",
                )}
              >
                <input
                  id={id}
                  type="radio"
                  name="accent-preference"
                  value={choice}
                  checked={checked}
                  onChange={() => setAccent(choice)}
                  className="sr-only"
                />
                <span
                  aria-hidden
                  className="size-8 rounded-full border border-border"
                  style={{ background: ACCENT_SWATCH[choice] }}
                />
                <span className="text-micro text-text-2">{accentLabels[choice]}</span>
              </label>
            );
          })}
        </div>
      </div>
    </fieldset>
  );
}
