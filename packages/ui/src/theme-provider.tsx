"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  resolveInitialTheme,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemeChoice,
} from "./theme-script";

type ThemeContextValue = {
  /** The user's choice: "light" | "dark" | "system". */
  theme: ThemeChoice;
  /** The concrete palette in effect (system collapsed to light/dark). */
  resolvedTheme: ResolvedTheme;
  /** Persist a new choice and apply it immediately. */
  setTheme: (theme: ThemeChoice) => void;
  /** Cycle light → dark → system → light. */
  cycleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const DARK_QUERY = "(prefers-color-scheme: dark)";
const CYCLE: readonly ThemeChoice[] = ["light", "dark", "system"];

function prefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia(DARK_QUERY).matches;
}

function readStoredChoice(): ThemeChoice {
  if (typeof window === "undefined") {
    return "system";
  }
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    /* storage may be unavailable (private mode / disabled) */
  }
  return "system";
}

function applyResolvedTheme(resolved: ResolvedTheme): void {
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = resolved;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Initialise from storage/OS on mount. The pre-paint <ThemeScript/> has already
  // stamped data-theme, so this only syncs React state — no visible flash.
  const [theme, setThemeState] = useState<ThemeChoice>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const stored = readStoredChoice();
    setThemeState(stored);
    const resolved = resolveInitialTheme(stored === "system" ? null : stored, prefersDark());
    setResolvedTheme(resolved);
    applyResolvedTheme(resolved);
  }, []);

  // Follow OS changes only while the choice is "system".
  useEffect(() => {
    if (theme !== "system" || typeof window === "undefined") {
      return;
    }
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      const resolved: ResolvedTheme = mql.matches ? "dark" : "light";
      setResolvedTheme(resolved);
      applyResolvedTheme(resolved);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: ThemeChoice) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* ignore persistence failure */
    }
    const resolved = resolveInitialTheme(next === "system" ? null : next, prefersDark());
    setResolvedTheme(resolved);
    applyResolvedTheme(resolved);
  }, []);

  const cycleTheme = useCallback(() => {
    setTheme(CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length] ?? "system");
  }, [theme, setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme, cycleTheme }),
    [theme, resolvedTheme, setTheme, cycleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}
