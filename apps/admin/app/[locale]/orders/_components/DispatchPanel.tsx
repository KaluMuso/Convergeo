"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";

import { type OrderDetail, type OrderEvent, ordersApi } from "./api";
import {
  DEFAULT_DISPATCH_COURIER,
  DISPATCH_COURIERS,
  type DispatchCourier,
  isDispatchFormReady,
  requiresCourierOtherName,
} from "./dispatch-model";

type DispatchPanelProps = {
  order: OrderDetail;
  onSuccess: () => void;
};

const DISPATCH_EVENTS: OrderEvent[] = ["ship", "mark_delivered"];

export function DispatchPanel({ order, onSuccess }: DispatchPanelProps) {
  const t = useTranslations("admin.orders.dispatch");
  const [courier, setCourier] = useState<DispatchCourier>(DEFAULT_DISPATCH_COURIER);
  const [courierOther, setCourierOther] = useState("");
  const [trackingNote, setTrackingNote] = useState("");
  const [event, setEvent] = useState<OrderEvent>("ship");
  const [confirmedManual, setConfirmedManual] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [success, setSuccess] = useState(false);

  const ready = isDispatchFormReady({
    courier,
    courierOther,
    trackingNote,
    confirmedManual,
  });

  const submit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    setPermissionDenied(false);
    setSuccess(false);
    try {
      await ordersApi.request(`/admin/orders/${order.id}/dispatch`, {
        method: "POST",
        body: JSON.stringify({
          courier,
          courier_other: requiresCourierOtherName(courier) ? courierOther.trim() : null,
          tracking_note: trackingNote.trim(),
          event,
        }),
      });
      setSuccess(true);
      setConfirmedManual(false);
      onSuccess();
    } catch (err) {
      const classified = classifyAdminRequestError(err);
      if (classified.kind === "permission") {
        setPermissionDenied(true);
        setError(t("permissionDenied"));
      } else {
        setError(t("failure"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-3 rounded-md border border-border p-4">
      <h2 className="font-medium text-text">{t("title")}</h2>
      <p className="text-sm text-muted">{t("subtitle")}</p>
      <p className="text-xs text-muted">{t("manualModelHint")}</p>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("courier")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-border px-3"
          value={courier}
          onChange={(change) => setCourier(change.target.value as DispatchCourier)}
          data-testid="dispatch-courier"
        >
          {DISPATCH_COURIERS.map((value) => (
            <option key={value} value={value}>
              {t(`couriers.${value}`)}
            </option>
          ))}
        </select>
      </label>

      {requiresCourierOtherName(courier) ? (
        <label className="block space-y-1 text-sm">
          <span className="text-muted">{t("courierOther")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={courierOther}
            onChange={(change) => setCourierOther(change.target.value)}
            placeholder={t("courierOtherPlaceholder")}
          />
        </label>
      ) : null}

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("trackingNote")}</span>
        <textarea
          className="min-h-20 w-full rounded-md border border-border px-3 py-2"
          value={trackingNote}
          onChange={(change) => setTrackingNote(change.target.value)}
          placeholder={t("trackingPlaceholder")}
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("statusEvent")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-border px-3"
          value={event}
          onChange={(change) => setEvent(change.target.value as OrderEvent)}
        >
          {DISPATCH_EVENTS.map((value) => (
            <option key={value} value={value}>
              {t(`events.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex min-h-11 items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4"
          checked={confirmedManual}
          onChange={(change) => setConfirmedManual(change.target.checked)}
          data-testid="dispatch-confirm-manual"
        />
        <span className="text-muted">{t("confirmManual")}</span>
      </label>

      {permissionDenied ? (
        <p className="text-sm text-warning">{error}</p>
      ) : error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : null}
      {success ? <p className="text-sm text-success">{t("success")}</p> : null}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={submitting || !ready}
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </section>
  );
}
