"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmModal } from "../../_components/ConfirmModal";

import { type OrderDetail, type OrderEvent, ordersApi } from "./api";
import {
  allowedAdminActions,
  CANCELLATION_EVENTS,
  isDispatchEvent,
  isPrepaidUnpaid,
  needsRefundPath,
  type OrderGuardInput,
} from "./order-transitions";

type InterventionPanelProps = {
  order: OrderDetail;
  guard: OrderGuardInput;
  payoutsOn: boolean;
  onSuccess: () => void;
};

export function InterventionPanel({ order, guard, payoutsOn, onSuccess }: InterventionPanelProps) {
  const t = useTranslations("admin.orders.intervention");
  // Ship / mark-delivered carry courier details, so they live in the dispatch panel.
  const actions = allowedAdminActions(guard).filter((action) => !isDispatchEvent(action.event));
  const dispatchOffered = allowedAdminActions(guard).some((action) =>
    isDispatchEvent(action.event),
  );
  const [pending, setPending] = useState<OrderEvent | null>(null);
  const [reason, setReason] = useState("");
  const [refundPath, setRefundPath] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const target = pending ? actions.find((action) => action.event === pending) : undefined;
  const destructive = pending ? CANCELLATION_EVENTS.includes(pending) : false;
  const refundRequired = pending ? needsRefundPath(guard, pending) : false;

  const close = () => {
    setPending(null);
    setReason("");
    setRefundPath(false);
    setError(null);
  };

  const submit = async (): Promise<boolean> => {
    if (!pending) return false;
    setError(null);
    try {
      await ordersApi.request(`/admin/orders/${order.id}/intervene`, {
        method: "POST",
        body: JSON.stringify({
          event: pending,
          reason: reason.trim(),
          refund_path: refundRequired ? refundPath : false,
        }),
      });
      setSuccess(true);
      onSuccess();
      return true;
    } catch {
      setError(t("failure"));
      return false;
    }
  };

  return (
    <section
      aria-labelledby="next-actions-heading"
      className="space-y-3 rounded-lg border border-border bg-surface p-4"
      data-testid="next-actions"
    >
      <h2 id="next-actions-heading" className="font-medium text-text">
        {t("title")}
      </h2>
      <p className="text-sm text-muted">
        {t("subtitle", { status: t(`statuses.${order.status}`) })}
      </p>

      {isPrepaidUnpaid(guard) ? (
        <p
          role="note"
          className="rounded-md border border-warning/40 bg-warning/5 p-3 text-sm text-text"
        >
          {t("prepaidUnpaid")}
        </p>
      ) : null}

      {actions.length === 0 && !dispatchOffered ? (
        <p className="text-sm text-muted" data-testid="no-actions">
          {t("terminal")}
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => {
            const cancels = CANCELLATION_EVENTS.includes(action.event);
            return (
              <button
                key={action.event}
                type="button"
                data-testid={`action-${action.event}`}
                onClick={() => {
                  setSuccess(false);
                  setPending(action.event);
                }}
                className={`inline-flex min-h-11 items-center rounded-md px-4 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
                  cancels
                    ? "border border-danger text-danger"
                    : "bg-primary text-[var(--primary-btn-fg)]"
                }`}
              >
                {t(`events.${action.event}`)}
              </button>
            );
          })}
        </div>
      )}
      {dispatchOffered ? <p className="text-xs text-muted">{t("useDispatchBelow")}</p> : null}
      {success ? (
        <p role="status" className="text-sm text-success">
          {t("success")}
        </p>
      ) : null}

      <ConfirmModal
        open={pending !== null}
        title={pending ? t(`events.${pending}`) : ""}
        destructive={destructive}
        confirmLabel={pending ? t(`events.${pending}`) : ""}
        canConfirm={reason.trim().length > 0 && (!refundRequired || refundPath)}
        onConfirm={submit}
        onClose={close}
        error={error}
        data-testid="intervention-confirm"
        summary={
          target ? (
            <div className="space-y-2">
              <p>
                {t("willChange", {
                  from: t(`statuses.${order.status}`),
                  to: t(`statuses.${target.to}`),
                })}
              </p>
              {destructive ? <p className="font-medium text-danger">{t("irreversible")}</p> : null}
              {refundRequired && !payoutsOn ? (
                <p className="text-warning">{t("refundQueuedNotSent")}</p>
              ) : null}
            </div>
          ) : null
        }
      >
        <label className="block space-y-1 text-sm">
          <span className="text-text-2">{t("reason")}</span>
          <textarea
            className="min-h-20 w-full rounded-md border border-border bg-surface px-3 py-2"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t("reasonPlaceholder")}
            required
          />
        </label>
        {refundRequired ? (
          <label className="flex min-h-11 items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4"
              checked={refundPath}
              onChange={(event) => setRefundPath(event.target.checked)}
            />
            <span>{t("refundPath")}</span>
          </label>
        ) : null}
      </ConfirmModal>
    </section>
  );
}
