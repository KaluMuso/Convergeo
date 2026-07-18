"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";

import { MANUAL_ESCROW_CONFIRMATION, type OrderDetail, ordersApi } from "./api";
import { summarizeOrderLedger } from "./ledger-summary";

type EscrowPanelProps = {
  order: OrderDetail;
  onSuccess: () => void;
};

export function EscrowPanel({ order, onSuccess }: EscrowPanelProps) {
  const t = useTranslations("admin.orders.escrow");
  const [operation, setOperation] = useState<"hold" | "release">("hold");
  const [amountNgwee, setAmountNgwee] = useState("");
  const [reason, setReason] = useState("");
  const [confirmationPhrase, setConfirmationPhrase] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [success, setSuccess] = useState(false);

  const ledgerSummary = useMemo(() => summarizeOrderLedger(order.ledger), [order.ledger]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setPermissionDenied(false);
    setSuccess(false);
    const parsedAmount = Number.parseInt(amountNgwee, 10);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError(t("invalidAmount"));
      setSubmitting(false);
      return;
    }
    if (confirmationPhrase.trim() !== MANUAL_ESCROW_CONFIRMATION) {
      setError(t("confirmationMismatch"));
      setSubmitting(false);
      return;
    }
    try {
      await ordersApi.request(`/admin/orders/${order.id}/escrow`, {
        method: "POST",
        body: JSON.stringify({
          operation,
          amount_ngwee: parsedAmount,
          reason: reason.trim(),
          confirmation_phrase: confirmationPhrase.trim(),
        }),
      });
      setSuccess(true);
      setAmountNgwee("");
      setReason("");
      setConfirmationPhrase("");
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
      <p className="text-xs text-muted">{t("readOnlyHint")}</p>
      <p className="text-xs text-muted">{t("dependency")}</p>

      <div
        className="rounded-md border border-border bg-bg p-3 text-sm"
        data-testid="escrow-ledger-summary"
      >
        <p className="font-medium text-text">{t("ledgerSummaryTitle")}</p>
        {ledgerSummary.transactionCount === 0 ? (
          <p className="mt-1 text-muted">{t("ledgerEmpty")}</p>
        ) : (
          <ul className="mt-2 space-y-1 text-xs text-muted">
            <li>{t("ledgerTxnCount", { count: ledgerSummary.transactionCount })}</li>
            <li>{t("ledgerPostingCount", { count: ledgerSummary.postingCount })}</li>
            <li className="font-mono">
              {t("ledgerKinds", { kinds: ledgerSummary.kinds.join(", ") })}
            </li>
          </ul>
        )}
      </div>

      <p className="text-xs text-muted">
        {t("confirmationHint", { phrase: MANUAL_ESCROW_CONFIRMATION })}
      </p>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("operation")}</span>
        <select
          className="min-h-11 w-full rounded-md border border-border px-3"
          value={operation}
          onChange={(change) => setOperation(change.target.value as typeof operation)}
        >
          <option value="hold">{t("operations.hold")}</option>
          <option value="release">{t("operations.release")}</option>
        </select>
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("amountNgwee")}</span>
        <input
          className="min-h-11 w-full rounded-md border border-border px-3 font-mono"
          inputMode="numeric"
          value={amountNgwee}
          onChange={(change) => setAmountNgwee(change.target.value)}
          placeholder={t("amountPlaceholder")}
          data-testid="escrow-amount"
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("reason")}</span>
        <textarea
          className="min-h-20 w-full rounded-md border border-border px-3 py-2"
          value={reason}
          onChange={(change) => setReason(change.target.value)}
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span className="text-muted">{t("confirmationPhrase")}</span>
        <input
          className="min-h-11 w-full rounded-md border border-border px-3 font-mono"
          value={confirmationPhrase}
          onChange={(change) => setConfirmationPhrase(change.target.value)}
          placeholder={MANUAL_ESCROW_CONFIRMATION}
        />
      </label>

      {permissionDenied ? (
        <p className="text-sm text-warning">{error}</p>
      ) : error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : null}
      {success ? <p className="text-sm text-success">{t("success")}</p> : null}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-danger px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={submitting || !reason.trim() || !confirmationPhrase.trim() || !amountNgwee.trim()}
        onClick={() => void submit()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </section>
  );
}
