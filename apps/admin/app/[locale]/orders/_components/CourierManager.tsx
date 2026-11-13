"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";

import { ordersApi } from "./api";
import {
  buildCourierPayload,
  type Courier,
  type CourierFormState,
  courierToForm,
  type DeliveryZone,
} from "./dispatch-board-model";

type CourierManagerProps = {
  couriers: Courier[];
  zones: DeliveryZone[];
  onChanged: () => void;
};

export function CourierManager({ couriers, zones, onChanged }: CourierManagerProps) {
  const t = useTranslations("admin.dispatch.couriers");
  const zoneKeys = zones.map((zone) => zone.zone_key);
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<CourierFormState>(() => courierToForm(null, zoneKeys));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const startEdit = (courier: Courier | null) => {
    setForm(courierToForm(courier, zoneKeys));
    setEditingId(courier ? courier.id : "new");
    setError(null);
    setNotice(null);
  };

  const save = async () => {
    const built = buildCourierPayload(form);
    if (!built.ok) {
      setError(t(`errors.${built.error}`));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const isNew = editingId === "new";
      await ordersApi.request(
        isNew ? "/admin/dispatch/couriers" : `/admin/dispatch/couriers/${editingId}`,
        { method: isNew ? "POST" : "PATCH", body: JSON.stringify(built.payload) },
      );
      setEditingId(null);
      setNotice(t("saved"));
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.code === "courier_name_taken") {
        setError(t("errors.taken"));
      } else if (classifyAdminRequestError(err).kind === "permission") {
        setError(t("errors.permission"));
      } else {
        setError(t("errors.generic"));
      }
    } finally {
      setSaving(false);
    }
  };

  const zoneLabel = (key: string) => zones.find((zone) => zone.zone_key === key)?.label ?? key;

  return (
    <section
      className="space-y-3 rounded-md border border-border p-4"
      aria-labelledby="couriers-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="couriers-heading" className="font-medium text-text">
          {t("title")}
        </h2>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
          onClick={() => startEdit(null)}
        >
          {t("add")}
        </button>
      </div>

      {couriers.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}

      <ul className="divide-y divide-border">
        {couriers.map((courier) => (
          <li key={courier.id} className="flex flex-wrap items-start justify-between gap-2 py-3">
            <div className="space-y-1 text-sm">
              <p className="font-medium text-text">{courier.name}</p>
              <p className="text-xs text-muted">
                {t("contactLine", {
                  contact: [courier.contact_whatsapp_e164, courier.contact_email]
                    .filter(Boolean)
                    .join(" · "),
                })}
              </p>
              <p className="text-xs text-muted">
                {courier.zones.length === 0
                  ? t("zonesNone")
                  : courier.zones
                      .map((zone) =>
                        zone.price_ngwee === null
                          ? zoneLabel(zone.zone_key)
                          : t("zonePriceLine", {
                              label: zoneLabel(zone.zone_key),
                              price: formatK(zone.price_ngwee),
                            }),
                      )
                      .join(" · ")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-xs ${courier.active ? "text-success" : "text-muted"}`}>
                {courier.active ? t("active") : t("inactive")}
              </span>
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
                onClick={() => startEdit(courier)}
              >
                {t("edit")}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {editingId ? (
        <form
          className="space-y-3 rounded-md border border-border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <label className="block space-y-1 text-sm">
            <span className="text-muted">{t("name")}</span>
            <input
              className="min-h-11 w-full rounded-md border border-border px-3"
              maxLength={120}
              value={form.name}
              onChange={(change) => setForm({ ...form, name: change.target.value })}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("whatsapp")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3"
                inputMode="tel"
                value={form.whatsapp}
                placeholder={t("whatsappPlaceholder")}
                onChange={(change) => setForm({ ...form, whatsapp: change.target.value })}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("email")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3"
                type="email"
                value={form.email}
                placeholder={t("emailPlaceholder")}
                onChange={(change) => setForm({ ...form, email: change.target.value })}
              />
            </label>
          </div>
          <p className="text-xs text-muted">{t("manual")}</p>
          <p className="text-xs text-muted">{t("apiReserved")}</p>

          <fieldset className="space-y-2">
            <legend className="text-sm text-muted">{t("zones")}</legend>
            {zones.map((zone) => {
              const state = form.zones[zone.zone_key] ?? { enabled: false, priceKwacha: "" };
              return (
                <div key={zone.zone_key} className="flex flex-wrap items-center gap-3">
                  <label className="flex min-h-11 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={state.enabled}
                      onChange={(change) =>
                        setForm({
                          ...form,
                          zones: {
                            ...form.zones,
                            [zone.zone_key]: { ...state, enabled: change.target.checked },
                          },
                        })
                      }
                    />
                    <span>{t("zoneLabel", { label: zone.label })}</span>
                  </label>
                  {state.enabled ? (
                    <input
                      className="min-h-11 w-32 rounded-md border border-border px-3"
                      inputMode="decimal"
                      value={state.priceKwacha}
                      aria-label={t("zonePrice")}
                      placeholder={t("zonePrice")}
                      onChange={(change) =>
                        setForm({
                          ...form,
                          zones: {
                            ...form.zones,
                            [zone.zone_key]: { ...state, priceKwacha: change.target.value },
                          },
                        })
                      }
                    />
                  ) : null}
                </div>
              );
            })}
          </fieldset>

          <label className="block space-y-1 text-sm">
            <span className="text-muted">{t("notes")}</span>
            <textarea
              className="min-h-16 w-full rounded-md border border-border px-3 py-2"
              maxLength={1000}
              value={form.notes}
              onChange={(change) => setForm({ ...form, notes: change.target.value })}
            />
          </label>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={form.active}
              onChange={(change) => setForm({ ...form, active: change.target.checked })}
            />
            <span>{t("active")}</span>
          </label>

          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
              disabled={saving}
            >
              {saving ? t("saving") : t("save")}
            </button>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
              onClick={() => setEditingId(null)}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {notice ? <p className="text-sm text-success">{notice}</p> : null}
    </section>
  );
}
