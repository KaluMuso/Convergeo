"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { type AdminDecisionType, type DisputeDetail, disputesApi } from "./api";

type DecisionPanelProps = {
  detail: DisputeDetail;
  onDecided: () => void;
};

const RAILS = ["mtn", "airtel", "zamtel"] as const;

export function DecisionPanel({ detail, onDecided }: DecisionPanelProps) {
  const t = useTranslations("admin.disputes.detail.decision");
  const [decision, setDecision] = useState<AdminDecisionType>("full_refund");
  const [note, setNote] = useState("");
  const [partialNgwee, setPartialNgwee] = useState("");
  const [customerMomo, setCustomerMomo] = useState(detail.order.customer_phone ?? "");
  const [customerRail, setCustomerRail] = useState<(typeof RAILS)[number]>("mtn");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!detail.decidable) {
    return (
      <section className="rounded-md border border-border p-4">
        <h2 className="text-sm font-semibold text-text">{t("title")}</h2>
        <p className="mt-2 text-sm text-muted">{t("alreadyResolved")}</p>
        {detail.admin_decision ? (
          <p className="mt-2 text-sm text-text">{detail.admin_decision}</p>
        ) : null}
      </section>
    );
  }

  const submit = async () => {
    if (!note.trim()) {
      setError(t("noteRequired"));
      return;
    }

    const partialValue =
      decision === "partial_refund" ? Number.parseInt(partialNgwee, 10) : undefined;
    if (decision === "partial_refund") {
      if (!partialValue || partialValue <= 0) {
        setError(t("partialRequired"));
        return;
      }
      if (partialValue > detail.order.order_total_ngwee) {
        setError(t("partialTooHigh", { max: formatK(detail.order.order_total_ngwee) }));
        return;
      }
    }

    if (!customerMomo.trim()) {
      setError(t("momoRequired"));
      return;
    }

    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      await disputesApi.request(`/admin/disputes/${detail.id}/decide`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          note: note.trim(),
          partial_refund_ngwee: partialValue ?? null,
          customer_momo: customerMomo.trim(),
          customer_rail: customerRail,
        }),
      });
      setMessage(t("success"));
      onDecided();
    } catch {
      setError(t("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4 rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-text">{t("title")}</h2>
      <p className="text-sm text-muted">{t("subtitle")}</p>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-text">{t("outcome")}</legend>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            checked={decision === "full_refund"}
            name="decision"
            type="radio"
            value="full_refund"
            onChange={() => setDecision("full_refund")}
          />
          {t("fullRefund")}
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            checked={decision === "partial_refund"}
            name="decision"
            type="radio"
            value="partial_refund"
            onChange={() => setDecision("partial_refund")}
          />
          {t("partialRefund")}
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            checked={decision === "release"}
            name="decision"
            type="radio"
            value="release"
            onChange={() => setDecision("release")}
          />
          {t("release")}
        </label>
      </fieldset>

      {decision === "partial_refund" ? (
        <label className="block space-y-1 text-sm">
          <span>{t("partialAmount", { max: formatK(detail.order.order_total_ngwee) })}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-2 font-mono"
            inputMode="numeric"
            type="number"
            value={partialNgwee}
            onChange={(event) => setPartialNgwee(event.target.value)}
          />
        </label>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span>{t("customerMomo")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-2"
            type="tel"
            value={customerMomo}
            onChange={(event) => setCustomerMomo(event.target.value)}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span>{t("customerRail")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-border px-2"
            value={customerRail}
            onChange={(event) => setCustomerRail(event.target.value as (typeof RAILS)[number])}
          >
            {RAILS.map((rail) => (
              <option key={rail} value={rail}>
                {t(`rails.${rail}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="block space-y-1 text-sm">
        <span>{t("note")}</span>
        <textarea
          className="min-h-24 w-full rounded-md border border-border p-2"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>

      <button
        type="button"
        disabled={submitting}
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>

      {message ? <p className="text-sm text-success">{message}</p> : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </section>
  );
}
