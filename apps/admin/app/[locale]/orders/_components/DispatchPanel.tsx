"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type OrderDetail, type OrderEvent, ordersApi } from "./api";

type DispatchPanelProps = {
  order: OrderDetail;
  onSuccess: () => void;
};

const DISPATCH_EVENTS: OrderEvent[] = ["ship", "mark_delivered"];

export function DispatchPanel({ order, onSuccess }: DispatchPanelProps) {
  const t = useTranslations("admin.orders.dispatch");
  const [courier, setCourier] = useState<"yango" | "indrive" | "other">("yango");
  const [courierOther, setCourierOther] = useState("");
  const [trackingNote, setTrackingNote] = useState("");
  const [event, setEvent] = useState<OrderEvent>("ship");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await ordersApi.request(`/admin/orders/${order.id}/dispatch`, {
        method: "POST",
        body: JSON.stringify({
          courier,
          courier_other: courier === "other" ? courierOther : null,
          tracking_note: trackingNote,
          event,
        }),
      });
      setSuccess(true);
      onSuccess();
    } catch {
      setError(t("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-3 rounded-md border border-[#E8DFD0] p-4">
      <h2 className="font-medium text-[#2A2118]">{t("title")}</h2>
      <p className="text-sm text-[#6B5E4C]">{t("subtitle")}</p>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("courier")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
          value={courier}
          onChange={(event) => setCourier(event.target.value as typeof courier)}
        >
          <option value="yango">{t("couriers.yango")}</option>
          <option value="indrive">{t("couriers.indrive")}</option>
          <option value="other">{t("couriers.other")}</option>
        </select>
      </label>

      {courier === "other" ? (
        <label className="block space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("courierOther")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
            value={courierOther}
            onChange={(event) => setCourierOther(event.target.value)}
          />
        </label>
      ) : null}

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("trackingNote")}</span>
        <textarea
          className="min-h-20 w-full rounded-md border border-[#E8DFD0] px-3 py-2"
          value={trackingNote}
          onChange={(event) => setTrackingNote(event.target.value)}
          placeholder={t("trackingPlaceholder")}
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("statusEvent")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
          value={event}
          onChange={(event) => setEvent(event.target.value as OrderEvent)}
        >
          {DISPATCH_EVENTS.map((value) => (
            <option key={value} value={value}>
              {t(`events.${value}`)}
            </option>
          ))}
        </select>
      </label>

      {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}
      {success ? <p className="text-sm text-[#276749]">{t("success")}</p> : null}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={submitting || !trackingNote.trim()}
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </section>
  );
}
