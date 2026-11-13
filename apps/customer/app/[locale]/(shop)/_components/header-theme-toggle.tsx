"use client";

import { useTheme } from "@vergeo/ui/src/theme-provider";

type HeaderThemeToggleProps = {
  labels: { label: string; light: string; dark: string; system: string };
  /** Phones: show the word under the icon so the button is not a bare icon. */
  caption?: boolean;
};

/**
 * Quick appearance switch in the header: cycles System → Light → Dark.
 * The full radio choice lives in Account → Preferences. Persisted per device
 * (localStorage via ThemeProvider); there is no profile field for it yet.
 */
export function HeaderThemeToggle({ labels, caption = false }: HeaderThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const order = ["system", "light", "dark"] as const;
  const next = order[(order.indexOf(theme) + 1) % order.length] ?? "system";
  const current = theme === "light" ? labels.light : theme === "dark" ? labels.dark : labels.system;

  return (
    <button
      type="button"
      data-testid="header-theme-toggle"
      aria-label={`${labels.label}: ${current}`}
      title={`${labels.label}: ${current}`}
      onClick={() => setTheme(next)}
      className={
        caption
          ? "inline-flex min-h-11 min-w-11 flex-col items-center justify-center gap-0.5 rounded px-1 text-micro font-semibold text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
          : "inline-flex min-h-11 min-w-11 items-center justify-center rounded text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
      }
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {theme === "dark" ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
        ) : theme === "light" ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        ) : (
          <>
            <rect x="3" y="4" width="18" height="12" rx="2" />
            <path d="M8 20h8M12 16v4" />
          </>
        )}
      </svg>
      {caption ? <span aria-hidden>{labels.label}</span> : null}
    </button>
  );
}
