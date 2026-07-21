"use client";

import { PUBLIC_LOCALES } from "@vergeo/i18n";
import { usePathname } from "next/navigation";

import { swapLocaleInPath } from "../../../lib/locale-path";

export type LocaleSwitcherLabels = {
  ariaLabel: string;
  names: Record<string, string>;
};

type LocaleSwitcherProps = {
  locale: string;
  labels: LocaleSwitcherLabels;
};

/**
 * Footer locale control — preserves the current route when switching language.
 */
export function LocaleSwitcher({ locale, labels }: LocaleSwitcherProps) {
  const pathname = usePathname();

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextLocale = event.target.value;
    if (nextLocale === locale) {
      return;
    }

    const nextPath = swapLocaleInPath(pathname, nextLocale);
    const query = window.location.search;
    window.location.assign(query ? `${nextPath}${query}` : nextPath);
  };

  return (
    <label
      className="inline-flex min-h-11 items-center gap-2 text-micro"
      style={{ color: "var(--panel-muted)" }}
    >
      <span className="sr-only">{labels.ariaLabel}</span>
      <select
        value={locale}
        onChange={handleChange}
        aria-label={labels.ariaLabel}
        data-testid="locale-switcher"
        className="min-h-11 rounded border border-[color:var(--panel-border)] bg-[color:var(--panel)] px-2 text-micro text-[color:var(--panel-text)]"
      >
        {PUBLIC_LOCALES.map((code) => (
          <option key={code} value={code}>
            {labels.names[code] ?? code}
          </option>
        ))}
      </select>
    </label>
  );
}
