"use client";

import { useTheme } from "./theme-provider";

import type { ThemeChoice } from "./theme-script";

export type ThemeToggleProps = {
  /** Accessible group label, e.g. "Theme". */
  label: string;
  /** Localised name for each mode (announced as the current state). */
  lightLabel: string;
  darkLabel: string;
  systemLabel: string;
  className?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function ThemeIcon({ choice }: { choice: ThemeChoice }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (choice === "light") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
      </svg>
    );
  }
  if (choice === "dark") {
    return (
      <svg {...common}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="2" y="4" width="20" height="14" rx="2" />
      <path d="M8 21h8m-4-3v3" />
    </svg>
  );
}

/**
 * Cycling theme control (light → dark → system). Renders as a single accessible
 * icon button; the current mode is surfaced via `aria-label` and `title` so the
 * choice is announced to assistive tech. Colours/focus come from design tokens,
 * so it flips with the palette automatically. All strings are injected by the
 * caller (next-intl) — no hardcoded copy.
 */
export function ThemeToggle({
  label,
  lightLabel,
  darkLabel,
  systemLabel,
  className,
}: ThemeToggleProps) {
  const { theme, cycleTheme } = useTheme();
  const modeLabel = theme === "light" ? lightLabel : theme === "dark" ? darkLabel : systemLabel;
  const accessibleLabel = `${label}: ${modeLabel}`;

  return (
    <button
      type="button"
      onClick={cycleTheme}
      title={accessibleLabel}
      aria-label={accessibleLabel}
      className={cx(
        "inline-flex min-h-11 min-w-11 items-center justify-center rounded-pill",
        "border border-border bg-surface text-text",
        "transition-colors duration-fast ease-std motion-reduce:transition-none",
        "hover:border-primary hover:text-primary",
        "focus-visible:outline-none focus-visible:shadow-focusRing",
        className,
      )}
    >
      <ThemeIcon choice={theme} />
    </button>
  );
}
