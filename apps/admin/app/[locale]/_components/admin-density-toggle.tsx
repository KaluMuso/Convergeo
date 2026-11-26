"use client";

import { useTranslations } from "next-intl";

import { useAdminDensity } from "./admin-density";

export function AdminDensityToggle() {
  const t = useTranslations("admin.shell.density");
  const { density, toggleDensity } = useAdminDensity();

  const next = density === "compact" ? t("comfortable") : t("compact");

  return (
    <button
      type="button"
      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-panel-muted/40 bg-transparent px-2 text-xs font-medium text-panel-text transition-transform press-scale hover:border-panel-text focus-visible:outline-none focus-visible:shadow-focusRing"
      onClick={toggleDensity}
      aria-pressed={density === "compact"}
      aria-label={t("label", { mode: next })}
      title={t("label", { mode: next })}
      data-testid="admin-density-toggle"
    >
      {density === "compact" ? t("compactShort") : t("comfortableShort")}
    </button>
  );
}
