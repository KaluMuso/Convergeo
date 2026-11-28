"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type BusyMode } from "./api";

const LEVELS = [0, 1, 2, 3, 4] as const;

export function BusyModeEditor() {
  const t = useTranslations("admin.config");
  const [current, setCurrent] = useState<number | null>(null);
  const [selected, setSelected] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<BusyMode>("/admin/config/busy-mode");
      setCurrent(data.level);
      setSelected(data.level);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = async () => {
    setSaving(true);
    try {
      const data = await configApi.request<BusyMode>(
        "/admin/config/busy-mode",
        {
          method: "PUT",
          body: JSON.stringify({ level: selected }),
        },
      );
      setCurrent(data.level);
      emitToastKey("configSaved", { type: "success" });
    } catch {
      emitToastKey("actionFailed", { type: "error" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="busy-mode-editor">
      <p className="text-sm text-muted">
        {t("busyMode.current")}: <strong>{current}</strong>
      </p>
      <fieldset className="space-y-2">
        <legend className="sr-only">{t("busyMode.title")}</legend>
        {LEVELS.map((level) => (
          <label
            key={level}
            className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-border p-3"
          >
            <input
              type="radio"
              name="busy-level"
              value={level}
              checked={selected === level}
              onChange={() => setSelected(level)}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium text-text">
                {t(`busyMode.level${level}`)}
              </span>
              <span className="block text-xs text-muted">
                {t(`busyMode.level${level}Body`)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      <button
        type="button"
        disabled={saving || selected === current}
        onClick={() => void apply()}
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-50"
      >
        {saving ? t("busyMode.applying") : t("busyMode.apply")}
      </button>
    </div>
  );
}
