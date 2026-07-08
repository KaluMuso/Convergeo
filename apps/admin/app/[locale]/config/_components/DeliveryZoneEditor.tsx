"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type DeliveryZone } from "./api";

export function DeliveryZoneEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<DeliveryZone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<DeliveryZone[]>("/admin/config/delivery-zones");
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

  const saveRow = async (zone: DeliveryZone) => {
    await configApi.request(`/admin/config/delivery-zones/${zone.zone_key}`, {
      method: "PATCH",
      body: JSON.stringify({
        label: zone.label,
        fee_ngwee: zone.fee_ngwee,
        active: zone.active,
      }),
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
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#E8DFD0] text-xs uppercase text-[#6B5E4C]">
          <tr>
            <th className="px-2 py-2">{t("deliveryZones.zoneKey")}</th>
            <th className="px-2 py-2">{t("common.label")}</th>
            <th className="px-2 py-2">{t("deliveryZones.feeNgwee")}</th>
            <th className="px-2 py-2">{t("deliveryZones.active")}</th>
            <th className="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.zone_key} className="border-b border-[#F0E8DC]">
              <td className="px-2 py-3 font-mono">{row.zone_key}</td>
              <td className="px-2 py-3">
                <input
                  className="min-h-11 w-full min-w-40 rounded-md border border-[#E8DFD0] px-2"
                  value={row.label}
                  onChange={(event) =>
                    setRows((prev) =>
                      prev.map((item, i) =>
                        i === index ? { ...item, label: event.target.value } : item,
                      ),
                    )
                  }
                />
              </td>
              <td className="px-2 py-3">
                <input
                  type="number"
                  min={0}
                  className="min-h-11 w-28 rounded-md border border-[#E8DFD0] px-2 font-mono"
                  value={row.fee_ngwee}
                  onChange={(event) =>
                    setRows((prev) =>
                      prev.map((item, i) =>
                        i === index ? { ...item, fee_ngwee: Number(event.target.value) } : item,
                      ),
                    )
                  }
                />
              </td>
              <td className="px-2 py-3">
                <label className="inline-flex min-h-11 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={row.active}
                    onChange={(event) =>
                      setRows((prev) =>
                        prev.map((item, i) =>
                          i === index ? { ...item, active: event.target.checked } : item,
                        ),
                      )
                    }
                  />
                  <span>{row.active ? t("common.active") : t("common.inactive")}</span>
                </label>
              </td>
              <td className="px-2 py-3">
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-3 text-sm font-medium text-white"
                  onClick={() => void saveRow(row)}
                >
                  {t("common.save")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
