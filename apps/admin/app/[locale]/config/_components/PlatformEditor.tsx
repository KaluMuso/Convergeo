"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type PlatformConfigEntry } from "./api";
import { ConfirmDiffDialog } from "./ConfirmDiffDialog";

const PLATFORM_LABEL_KEYS: Record<string, string> = {
  cod_cap_ngwee: "platform.codCap",
  free_delivery_threshold_ngwee: "platform.freeDelivery",
  reservation_ttl_min: "platform.reservationTtl",
  ai_guest_quota: "platform.aiGuestQuota",
  ai_free_monthly_quota: "platform.aiFreeQuota",
  ai_monthly_cap_usd: "platform.aiCapUsd",
  release_after_delivered_hours: "platform.releaseDelivered",
  release_after_shipped_days: "platform.releaseShipped",
};

const DANGEROUS_KEYS = new Set(["cod_cap_ngwee"]);

export function PlatformEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<PlatformConfigEntry[]>([]);
  const [drafts, setDrafts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ key: string; from: number; to: number } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<PlatformConfigEntry[]>("/admin/config/platform");
      setRows(data);
      setDrafts(Object.fromEntries(data.map((row) => [row.key, row.value])));
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const requestSave = (key: string) => {
    const current = rows.find((row) => row.key === key);
    const next = drafts[key];
    if (current === undefined || next === undefined || next === current.value) {
      return;
    }
    setPending({ key, from: current.value, to: next });
  };

  const commitSave = async () => {
    if (!pending) {
      return;
    }
    await configApi.request(`/admin/config/platform/${pending.key}`, {
      method: "PATCH",
      body: JSON.stringify({ value: pending.to }),
    });
    setPending(null);
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
    <div className="space-y-4">
      <p className="text-sm text-[#9B2C2C]">{t("platform.dangerousHint")}</p>
      <div className="space-y-3">
        {rows.map((row) => (
          <div
            key={row.key}
            className="flex flex-col gap-2 rounded-md border border-[#E8DFD0] p-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="text-sm font-medium text-[#2A2118]">
                {t(PLATFORM_LABEL_KEYS[row.key] ?? "common.key")}
              </p>
              <p className="text-xs text-[#6B5E4C]">{row.description}</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                className="min-h-11 w-32 rounded-md border border-[#E8DFD0] px-2 font-mono"
                value={drafts[row.key] ?? row.value}
                onChange={(event) =>
                  setDrafts((prev) => ({ ...prev, [row.key]: Number(event.target.value) }))
                }
              />
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-3 text-sm font-medium text-white"
                onClick={() => requestSave(row.key)}
              >
                {t("common.save")}
              </button>
            </div>
          </div>
        ))}
      </div>

      <ConfirmDiffDialog
        open={pending !== null}
        dangerous={pending ? DANGEROUS_KEYS.has(pending.key) : false}
        fromLabel={t("confirm.from")}
        toLabel={t("confirm.to")}
        fromValue={pending ? String(pending.from) : ""}
        toValue={pending ? String(pending.to) : ""}
        onCancel={() => setPending(null)}
        onConfirm={commitSave}
      />
    </div>
  );
}
