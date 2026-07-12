"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type OrderDetail, type OrderEvent, ordersApi } from "./api";

type InterventionPanelProps = {
  order: OrderDetail;
  onSuccess: () => void;
};

const INTERVENTION_EVENTS: OrderEvent[] = [
  "confirm",
  "reject",
  "cancel",
  "start_processing",
  "ready_for_pickup",
  "ship",
  "verify_pickup",
  "mark_delivered",
  "confirm_received",
];

export function InterventionPanel({ order, onSuccess }: InterventionPanelProps) {
  const t = useTranslations("admin.orders.intervention");
  const [event, setEvent] = useState<OrderEvent>("confirm");
  const [reason, setReason] = useState("");
  const [refundPath, setRefundPath] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await ordersApi.request(`/admin/orders/${order.id}/intervene`, {
        method: "POST",
        body: JSON.stringify({
          event,
          reason,
          refund_path: refundPath,
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
    <section className="space-y-3 rounded-md border border-border p-4">
      <h2 className="font-medium text-text">{t("title")}</h2>
      <p className="text-sm text-muted">{t("subtitle", { status: order.status })}</p>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("event")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-border px-3"
          value={event}
          onChange={(event) => setEvent(event.target.value as OrderEvent)}
        >
          {INTERVENTION_EVENTS.map((value) => (
            <option key={value} value={value}>
              {t(`events.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("reason")}</span>
        <textarea
          className="min-h-20 w-full rounded-md border border-border px-3 py-2"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t("reasonPlaceholder")}
        />
      </label>

      <label className="flex min-h-11 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={refundPath}
          onChange={(event) => setRefundPath(event.target.checked)}
        />
        <span>{t("refundPath")}</span>
      </label>

      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {success ? <p className="text-sm text-success">{t("success")}</p> : null}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger disabled:opacity-60"
        disabled={submitting || !reason.trim()}
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </section>
  );
}
