"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  configApi,
  type AdminArea,
  type AreaDistance,
  type AreaPricingSettings,
  type TimeBand,
} from "./api";

const SETTINGS_URL = "/admin/logistics/area-pricing/settings";

const INT_FIELDS = [
  ["base_per_km_ngwee", "basePerKm"],
  ["stop_fee_ngwee", "stopFee"],
  ["min_fee_ngwee", "minFee"],
  ["max_fee_ngwee", "maxFee"],
  ["intra_area_metres", "intraArea"],
  ["rain_multiplier_bps", "rainMultiplier"],
  ["quote_ttl_minutes", "quoteTtl"],
] as const;

type IntField = (typeof INT_FIELDS)[number][0];

const INPUT = "min-h-11 rounded-md border border-border px-2 font-mono";
const BUTTON =
  "inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-white";
const SECONDARY = "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm";

/** Whole numbers only: money is integer ngwee, multipliers basis points. */
export function toWholeNumber(raw: string): number | null {
  return /^\d{1,9}$/.test(raw.trim()) ? Number.parseInt(raw.trim(), 10) : null;
}

/** Road km as a decimal string, at most two places (sent as text, never a float). */
export function isRoadKm(raw: string): boolean {
  return /^\d{1,3}(\.\d{1,2})?$/.test(raw.trim());
}

function SettingsForm() {
  const t = useTranslations("admin.config");
  const [settings, setSettings] = useState<AreaPricingSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<IntField, string>>({} as Record<IntField, string>);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      const data = await configApi.request<AreaPricingSettings>(SETTINGS_URL);
      setSettings(data);
      setDrafts(
        Object.fromEntries(INT_FIELDS.map(([field]) => [field, String(data[field])])) as Record<
          IntField,
          string
        >,
      );
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{t("common.error")}</p>
        <button type="button" className={SECONDARY} onClick={() => void load()}>
          {t("common.retry")}
        </button>
      </div>
    );
  }
  if (!settings) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  const setBand = (index: number, patch: Partial<TimeBand>) =>
    setSettings({
      ...settings,
      time_bands: settings.time_bands.map((band, i) =>
        i === index ? { ...band, ...patch } : band,
      ),
    });

  const save = async () => {
    const body: AreaPricingSettings = { ...settings };
    for (const [field] of INT_FIELDS) {
      const value = toWholeNumber(drafts[field] ?? "");
      if (value === null) {
        emitToastKey("actionFailed", { type: "error" });
        return;
      }
      body[field] = value;
    }
    try {
      await configApi.request(SETTINGS_URL, { method: "PUT", body: JSON.stringify(body) });
    } catch {
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    emitToastKey("configSaved", { type: "success" });
    await load();
  };

  return (
    <section className="space-y-3" aria-labelledby="area-pricing-formula">
      <h3 id="area-pricing-formula" className="font-medium text-text">
        {t("areaPricing.formulaTitle")}
      </h3>
      <p className="text-sm text-muted">{t("areaPricing.formulaHint")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {INT_FIELDS.map(([field, labelKey]) => (
          <label key={field} className="flex flex-col gap-1 text-sm">
            <span>{t(`areaPricing.${labelKey}`)}</span>
            <input
              inputMode="numeric"
              className={INPUT}
              value={drafts[field] ?? ""}
              onChange={(event) => setDrafts({ ...drafts, [field]: event.target.value })}
            />
          </label>
        ))}
        <label className="inline-flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.zone_bounds}
            onChange={(event) => setSettings({ ...settings, zone_bounds: event.target.checked })}
          />
          <span>{t("areaPricing.zoneBounds")}</span>
        </label>
      </div>

      <h4 className="pt-2 text-sm font-medium text-text">{t("areaPricing.bandsTitle")}</h4>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border text-xs uppercase text-muted">
            <tr>
              <th className="px-2 py-2">{t("common.key")}</th>
              <th className="px-2 py-2">{t("areaPricing.bandStart")}</th>
              <th className="px-2 py-2">{t("areaPricing.bandEnd")}</th>
              <th className="px-2 py-2">{t("areaPricing.bandMultiplier")}</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {settings.time_bands.map((band, index) => (
              <tr key={index} className="border-b border-border">
                <td className="px-2 py-2">
                  <input
                    className={`${INPUT} w-36`}
                    value={band.key}
                    onChange={(event) => setBand(index, { key: event.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    type="time"
                    className={INPUT}
                    value={band.start}
                    onChange={(event) => setBand(index, { start: event.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    type="time"
                    className={INPUT}
                    value={band.end}
                    onChange={(event) => setBand(index, { end: event.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    inputMode="numeric"
                    className={`${INPUT} w-24`}
                    value={String(band.multiplier_bps)}
                    onChange={(event) =>
                      setBand(index, {
                        multiplier_bps: toWholeNumber(event.target.value) ?? 0,
                      })
                    }
                  />
                </td>
                <td className="px-2 py-2">
                  <button
                    type="button"
                    className={SECONDARY}
                    onClick={() =>
                      setSettings({
                        ...settings,
                        time_bands: settings.time_bands.filter((_, i) => i !== index),
                      })
                    }
                  >
                    {t("areaPricing.removeBand")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={SECONDARY}
          onClick={() =>
            setSettings({
              ...settings,
              time_bands: [
                ...settings.time_bands,
                { key: "", start: "20:00", end: "21:00", multiplier_bps: 10000 },
              ],
            })
          }
        >
          {t("areaPricing.addBand")}
        </button>
        <button type="button" className={BUTTON} onClick={() => void save()}>
          {t("common.save")}
        </button>
      </div>
    </section>
  );
}

function DistanceTable() {
  const t = useTranslations("admin.config");
  const [areas, setAreas] = useState<AdminArea[]>([]);
  const [fromArea, setFromArea] = useState("");
  const [rows, setRows] = useState<AreaDistance[]>([]);
  const [bothWays, setBothWays] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    configApi
      .request<AdminArea[]>("/admin/logistics/areas")
      .then((data) => {
        setAreas(data);
        setFromArea((current) => current || data[0]?.slug || "");
      })
      .catch(() => setError(true));
  }, []);

  const loadRows = useCallback(async (slug: string) => {
    if (!slug) return;
    try {
      const data = await configApi.request<{ rows: AreaDistance[] }>(
        `/admin/logistics/area-distances?from_area=${encodeURIComponent(slug)}`,
      );
      setRows(data.rows);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void loadRows(fromArea);
  }, [fromArea, loadRows]);

  const names = Object.fromEntries(areas.map((area) => [area.slug, area.name]));

  const saveRow = async (row: AreaDistance) => {
    if (!isRoadKm(row.road_km)) {
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    try {
      await configApi.request(`/admin/logistics/area-distances/${row.from_area}/${row.to_area}`, {
        method: "PATCH",
        body: JSON.stringify({
          road_km: row.road_km.trim(),
          minutes: row.minutes,
          both_directions: bothWays,
        }),
      });
    } catch {
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    emitToastKey("configSaved", { type: "success" });
    await loadRows(fromArea);
  };

  const setRow = (index: number, patch: Partial<AreaDistance>) =>
    setRows((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  return (
    <section className="space-y-3" aria-labelledby="area-pricing-distances">
      <h3 id="area-pricing-distances" className="font-medium text-text">
        {t("areaPricing.distancesTitle")}
      </h3>
      <p className="text-sm text-muted">{t("areaPricing.distancesHint")}</p>
      {error ? <p className="text-sm text-danger">{t("common.error")}</p> : null}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span>{t("areaPricing.fromArea")}</span>
          <select
            className={INPUT}
            value={fromArea}
            onChange={(event) => setFromArea(event.target.value)}
          >
            {areas.map((area) => (
              <option key={area.slug} value={area.slug}>
                {area.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={bothWays}
            onChange={(event) => setBothWays(event.target.checked)}
          />
          <span>{t("areaPricing.bothWays")}</span>
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border text-xs uppercase text-muted">
            <tr>
              <th className="px-2 py-2">{t("areaPricing.toArea")}</th>
              <th className="px-2 py-2">{t("areaPricing.roadKm")}</th>
              <th className="px-2 py-2">{t("areaPricing.minutes")}</th>
              <th className="px-2 py-2">{t("areaPricing.source")}</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.to_area} className="border-b border-border">
                <td className="px-2 py-2">{names[row.to_area] ?? row.to_area}</td>
                <td className="px-2 py-2">
                  <input
                    inputMode="decimal"
                    className={`${INPUT} w-24`}
                    value={row.road_km}
                    onChange={(event) => setRow(index, { road_km: event.target.value })}
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    inputMode="numeric"
                    className={`${INPUT} w-20`}
                    value={String(row.minutes)}
                    onChange={(event) =>
                      setRow(index, { minutes: toWholeNumber(event.target.value) ?? 0 })
                    }
                  />
                </td>
                <td className="px-2 py-2 text-xs text-muted">
                  {row.manual_override ? t("areaPricing.manual") : row.source}
                </td>
                <td className="px-2 py-2">
                  <button type="button" className={BUTTON} onClick={() => void saveRow(row)}>
                    {t("common.save")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function AreaPricingEditor() {
  return (
    <div className="space-y-8">
      <SettingsForm />
      <DistanceTable />
    </div>
  );
}
