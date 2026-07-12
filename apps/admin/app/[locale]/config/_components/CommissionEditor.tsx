"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type CommissionRate, configApi } from "./api";
import { ConfirmDiffDialog } from "./ConfirmDiffDialog";

export function CommissionEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<CommissionRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, number>>({});
  const [pending, setPending] = useState<{
    categoryKey: string;
    from: number;
    to: number;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<CommissionRate[]>("/admin/config/commissions");
      setRows(data);
      setDrafts(Object.fromEntries(data.map((row) => [row.category_key, row.rate_bps])));
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const requestSave = (categoryKey: string) => {
    const current = rows.find((row) => row.category_key === categoryKey);
    const next = drafts[categoryKey];
    if (current === undefined || next === undefined || next === current.rate_bps) {
      return;
    }
    setPending({ categoryKey, from: current.rate_bps, to: next });
  };

  const commitSave = async () => {
    if (!pending) {
      return;
    }
    await configApi.request(`/admin/config/commissions/${pending.categoryKey}`, {
      method: "PATCH",
      body: JSON.stringify({ rate_bps: pending.to }),
    });
    setPending(null);
    await load();
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
    <div className="space-y-4">
      <p className="text-sm text-danger">{t("commissions.dangerousHint")}</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border text-xs uppercase text-muted">
            <tr>
              <th className="px-2 py-2">{t("commissions.categoryKey")}</th>
              <th className="px-2 py-2">{t("commissions.rateBps")}</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.category_key} className="border-b border-border">
                <td className="px-2 py-3 font-mono">{row.category_key}</td>
                <td className="px-2 py-3">
                  <input
                    type="number"
                    min={0}
                    max={2000}
                    className="min-h-11 w-28 rounded-md border border-border px-2 font-mono"
                    value={drafts[row.category_key] ?? row.rate_bps}
                    onChange={(event) =>
                      setDrafts((prev) => ({
                        ...prev,
                        [row.category_key]: Number(event.target.value),
                      }))
                    }
                  />
                </td>
                <td className="px-2 py-3">
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-white"
                    onClick={() => requestSave(row.category_key)}
                  >
                    {t("common.save")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDiffDialog
        open={pending !== null}
        dangerous
        fromLabel={t("confirm.from")}
        toLabel={t("confirm.to")}
        fromValue={pending ? `${pending.from} bps` : ""}
        toValue={pending ? `${pending.to} bps` : ""}
        onCancel={() => setPending(null)}
        onConfirm={commitSave}
      />
    </div>
  );
}
