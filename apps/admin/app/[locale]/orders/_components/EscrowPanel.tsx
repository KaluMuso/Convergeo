"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { MANUAL_ESCROW_CONFIRMATION, type OrderDetail, ordersApi } from "./api";

type EscrowPanelProps = {
  order: OrderDetail;
  onSuccess: () => void;
};

export function EscrowPanel({ order, onSuccess }: EscrowPanelProps) {
  const t = useTranslations("admin.orders.escrow");
  const [operation, setOperation] = useState<"hold" | "release">("hold");
  const [amountNgwee, setAmountNgwee] = useState("10000");
  const [reason, setReason] = useState("");
  const [confirmationPhrase, setConfirmationPhrase] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    const parsedAmount = Number.parseInt(amountNgwee, 10);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError(t("invalidAmount"));
      setSubmitting(false);
      return;
    }
    try {
      await ordersApi.request(`/admin/orders/${order.id}/escrow`, {
        method: "POST",
        body: JSON.stringify({
          operation,
          amount_ngwee: parsedAmount,
          reason,
          confirmation_phrase: confirmationPhrase,
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
      <p className="text-xs text-[#6B5E4C]">
        {t("confirmationHint", { phrase: MANUAL_ESCROW_CONFIRMATION })}
      </p>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("operation")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
          value={operation}
          onChange={(event) => setOperation(event.target.value as typeof operation)}
        >
          <option value="hold">{t("operations.hold")}</option>
          <option value="release">{t("operations.release")}</option>
        </select>
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("amountNgwee")}</span>
        <input
          className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3 font-mono"
          inputMode="numeric"
          value={amountNgwee}
          onChange={(event) => setAmountNgwee(event.target.value)}
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("reason")}</span>
        <textarea
          className="min-h-20 w-full rounded-md border border-[#E8DFD0] px-3 py-2"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-[#6B5E4C]">{t("confirmationPhrase")}</span>
        <input
          className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3 font-mono"
          value={confirmationPhrase}
          onChange={(event) => setConfirmationPhrase(event.target.value)}
          placeholder={MANUAL_ESCROW_CONFIRMATION}
        />
      </label>

      {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}
      {success ? <p className="text-sm text-[#276749]">{t("success")}</p> : null}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-[#9B2C2C] px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={submitting || !reason.trim() || !confirmationPhrase.trim()}
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </section>
  );
}
