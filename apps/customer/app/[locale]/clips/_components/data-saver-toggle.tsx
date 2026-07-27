"use client";

import { useTranslations } from "next-intl";

/**
 * M17-P04 — the D-V2 data-saver switch.
 *
 * Presentational on purpose: the container owns the state so that exactly one
 * place decides whether video bytes may be fetched. A toggle that owned its own
 * persisted state would be a second source of truth for the same question.
 */
export function DataSaverToggle({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (next: boolean) => void;
}) {
  const t = useTranslations("clips");

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={t("a11y.saverToggleLabel")}
      data-testid="clips-data-saver-toggle"
      onClick={() => onChange(!on)}
      className="tap inline-flex min-h-11 items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span
        aria-hidden
        className={`inline-block h-3 w-3 rounded-full ${on ? "bg-success" : "bg-muted"}`}
      />
      <span>{on ? t("saver.on") : t("saver.off")}</span>
    </button>
  );
}
