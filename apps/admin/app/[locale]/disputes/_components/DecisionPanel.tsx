"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { payoutsEnabled } from "../../../../lib/payout-posture";
import { ConfirmModal } from "../../_components/ConfirmModal";

import { type AdminDecisionType, type DisputeDetail, disputesApi } from "./api";

type DecisionPanelProps = {
  detail: DisputeDetail;
  onDecided: () => void;
};

const RAILS = ["mtn", "airtel", "zamtel"] as const;

/** Server error: refunds are refused while payouts are disabled (no money moved). */
const REFUND_UNAVAILABLE_PAYOUTS_DISABLED = "dispute.refund_unavailable_payouts_disabled";

export function DecisionPanel({ detail, onDecided }: DecisionPanelProps) {
  const t = useTranslations("admin.disputes.detail.decision");
  const payoutsOn = payoutsEnabled();
  const [decision, setDecision] = useState<AdminDecisionType>(
    payoutsOn ? "full_refund" : "release",
  );
  const [confirming, setConfirming] = useState(false);
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

  const submit = () => {
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

    setError(null);
    setConfirming(true);
  };

  const execute = async (): Promise<boolean> => {
    // Defence in depth: refund outcomes are never sent while payouts are off,
    // even if the disabled radios were bypassed.
    if (!payoutsOn && decision !== "release") {
      setError(t("payoutsOffTitle"));
      return false;
    }
    const partialValue =
      decision === "partial_refund" ? Number.parseInt(partialNgwee, 10) : undefined;
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
      return true;
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === REFUND_UNAVAILABLE_PAYOUTS_DISABLED
          ? t("refundUnavailablePayoutsDisabled")
          : t("failure"),
      );
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const refundNgwee =
    decision === "full_refund"
      ? detail.order.order_total_ngwee
      : decision === "partial_refund"
        ? Number.parseInt(partialNgwee, 10) || 0
        : 0;

  return (
    <section className="space-y-4 rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-text">{t("title")}</h2>
      <p className="text-sm text-muted">{t("subtitle")}</p>

      {!payoutsOn ? (
        <div
          role="note"
          data-testid="payouts-disabled-note"
          className="space-y-1 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm"
        >
          <p className="font-medium text-text">{t("payoutsOffTitle")}</p>
          <p className="text-muted">{t("payoutsOffBody")}</p>
        </div>
      ) : null}

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-text">{t("outcome")}</legend>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            checked={decision === "full_refund"}
            disabled={!payoutsOn}
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
            disabled={!payoutsOn}
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
          {refundNgwee > 0 ? (
            <span className="block font-mono text-xs text-muted">
              {t("amountPreview", { amount: formatK(refundNgwee) })}
            </span>
          ) : null}
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
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)] disabled:opacity-60"
        onClick={submit}
      >
        {t("review")}
      </button>

      {message ? (
        <p role="status" className="text-sm text-success">
          {message}
        </p>
      ) : null}
      {error && !confirming ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      <ConfirmModal
        open={confirming}
        title={t("confirmTitle")}
        destructive={decision !== "release"}
        confirmLabel={t("submit")}
        onConfirm={execute}
        onClose={() => {
          setConfirming(false);
          setError(null);
        }}
        error={error}
        data-testid="dispute-confirm"
        summary={
          <div className="space-y-2">
            <p>{t(`confirmSummary.${decision}`, { amount: formatK(refundNgwee) })}</p>
            {decision !== "release" ? (
              <p className="font-mono text-xs">
                {t("refundTo", { momo: customerMomo, rail: t(`rails.${customerRail}`) })}
              </p>
            ) : null}
            <p className="text-xs text-muted">{t("noteRecorded")}</p>
          </div>
        }
      />
    </section>
  );
}
