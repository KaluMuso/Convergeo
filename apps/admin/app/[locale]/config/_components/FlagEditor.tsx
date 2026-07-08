"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type FeatureFlag } from "./api";

export function FlagEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<FeatureFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<FeatureFlag[]>("/admin/config/flags");
      setRows(data);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (flag: string, enabled: boolean) => {
    await configApi.request(`/admin/config/flags/${flag}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    await load();
  };

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{t("common.loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div
          key={row.flag}
          className="flex flex-col gap-2 rounded-md border border-[#E8DFD0] p-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p className="font-mono text-sm text-[#2A2118]">{row.flag}</p>
            <p className="text-xs text-[#6B5E4C]">{row.description}</p>
          </div>
          <label className="inline-flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              role="switch"
              checked={row.enabled}
              onChange={(event) => void toggle(row.flag, event.target.checked)}
            />
            <span className="text-sm">
              {row.enabled ? t("common.enabled") : t("common.disabled")}
            </span>
          </label>
        </div>
      ))}
    </div>
  );
}
