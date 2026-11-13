"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";

import { ordersApi } from "./api";
import {
  actionsFor,
  canNotify,
  classifyHandoverError,
  type Dispatch,
  type DispatchAction,
  doorPaymentActions,
  isHandoverCodeWellFormed,
  isPodPublicIdWellFormed,
  isStale,
  minutesWaiting,
  targetStatusFor,
  whatsAppShareUrl,
} from "./dispatch-board-model";

type DispatchCardProps = {
  dispatch: Dispatch;
  flagEnabled: boolean;
  doorPaymentEnabled?: boolean;
  onChanged: () => void;
};

const DOOR_ERROR_KEYS: Record<string, string> = {
  door_payment_in_flight: "inFlight",
  door_payment_attempts_exhausted: "attemptsExhausted",
  door_payment_cash_over_cap: "cashOverCap",
  door_payment_already_settled: "alreadySettled",
  door_payment_order_not_payable: "orderNotPayable",
  door_payment_invalid_phone: "invalidPhone",
  door_payment_operator_unsupported: "operatorUnsupported",
  door_payment_required: "required",
};

type MessageState = { text: string; whatsappTo: string | null } | null;

export function DispatchCard({
  dispatch,
  flagEnabled,
  doorPaymentEnabled = false,
  onChanged,
}: DispatchCardProps) {
  const t = useTranslations("admin.dispatch");
  const [openAction, setOpenAction] = useState<DispatchAction | null>(null);
  const [courierRef, setCourierRef] = useState(dispatch.courier_reference ?? "");
  const [reason, setReason] = useState("");
  const [podId, setPodId] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [message, setMessage] = useState<MessageState>(null);

  const actions = flagEnabled ? actionsFor(dispatch) : [];
  const stale = isStale(dispatch);

  const fail = (err: unknown) => {
    if (err instanceof ApiError && err.code === "dispatch_invalid_transition") {
      setError(t("errors.invalidTransition"));
      return;
    }
    if (err instanceof ApiError && err.code in DOOR_ERROR_KEYS) {
      setError(t(`doorPayment.errors.${DOOR_ERROR_KEYS[err.code]}`));
      return;
    }
    if (err instanceof ApiError && err.code === "feature_disabled") {
      setError(t("errors.disabled"));
      return;
    }
    const classified = classifyAdminRequestError(err);
    setError(classified.kind === "permission" ? t("errors.permissionDenied") : t("errors.generic"));
  };

  const run = async (path: string, body: Record<string, unknown>, success?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await ordersApi.request(path, { method: "POST", body: JSON.stringify(body) });
      setOpenAction(null);
      if (success) setNotice(success);
      onChanged();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const submitAction = async (action: DispatchAction) => {
    if (action === "verifyHandover") {
      if (!isHandoverCodeWellFormed(code)) {
        setError(t("errors.codeFormat"));
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await ordersApi.request(`/admin/dispatch/requests/${dispatch.id}/handover`, {
          method: "POST",
          body: JSON.stringify({ code: code.trim() }),
        });
        setCode("");
        setOpenAction(null);
        setNotice(t("handover.success"));
        onChanged();
      } catch (err) {
        if (err instanceof ApiError) {
          const handover = classifyHandoverError(err);
          if (handover.kind === "invalid") {
            setError(t("errors.handoverInvalid", { count: handover.attemptsRemaining ?? 0 }));
            return;
          }
          if (handover.kind === "locked") {
            const minutes = Math.max(1, Math.ceil((handover.retryAfter ?? 60) / 60));
            setError(t("errors.handoverLocked", { minutes }));
            return;
          }
          if (handover.kind === "rateLimited") {
            setError(t("errors.rateLimited"));
            return;
          }
        }
        fail(err);
      } finally {
        setBusy(false);
      }
      return;
    }

    const target = targetStatusFor(action);
    if (!target) return;
    if (action === "fail" && !reason.trim()) {
      setError(t("errors.reasonRequired"));
      return;
    }
    if (action === "deliverWithPhoto" && !isPodPublicIdWellFormed(podId)) {
      setError(t("errors.podFormat"));
      return;
    }
    await run(`/admin/dispatch/requests/${dispatch.id}/transition`, {
      to_status: target,
      courier_reference: courierRef.trim() || null,
      failure_reason: action === "fail" ? reason.trim() : null,
      pod_photo_public_id: action === "deliverWithPhoto" ? podId.trim() : null,
    });
  };

  const notify = async (channel: "whatsapp" | "email") => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await ordersApi.request<{ enqueued: boolean; text: string }>(
        `/admin/dispatch/requests/${dispatch.id}/notify`,
        { method: "POST", body: JSON.stringify({ channel }) },
      );
      setNotice(result.enqueued ? t("notify.queued", { channel }) : t("notify.duplicate"));
      onChanged();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const copyMessage = async () => {
    setError(null);
    setNotice(null);
    try {
      const result = await ordersApi.request<{ text: string; whatsapp_to: string | null }>(
        `/admin/dispatch/requests/${dispatch.id}/message`,
      );
      setMessage({ text: result.text, whatsappTo: result.whatsapp_to });
      try {
        await navigator.clipboard.writeText(result.text);
        setNotice(t("notify.copied"));
      } catch {
        setNotice(t("notify.copyFailed"));
      }
    } catch (err) {
      fail(err);
    }
  };

  const shareUrl = message ? whatsAppShareUrl(message.whatsappTo, message.text) : null;

  return (
    <li
      className="space-y-3 rounded-md border border-border p-4"
      data-testid={`dispatch-card-${dispatch.id}`}
      data-status={dispatch.status}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="font-mono text-sm text-text">{dispatch.order_reference}</p>
          <p className="text-xs text-muted">
            {t("active.meta", { courier: dispatch.courier_name, vendor: dispatch.vendor_name })}
          </p>
        </div>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text">
          {t(`statuses.${dispatch.status}`)}
        </span>
      </div>

      <div className="space-y-1 text-sm">
        <div>
          <p className="text-text">
            {dispatch.cod_amount_ngwee > 0
              ? t("active.codDue", { amount: formatK(dispatch.cod_amount_ngwee) })
              : t("active.prepaid")}
          </p>
        </div>
        {dispatch.quoted_price_ngwee !== null ? (
          <div>
            <p className="text-muted">
              {t("active.quoted", { amount: formatK(dispatch.quoted_price_ngwee) })}
            </p>
          </div>
        ) : null}
        {dispatch.courier_reference ? (
          <div>
            <p className="text-muted">
              {t("active.courierRef", { ref: dispatch.courier_reference })}
            </p>
          </div>
        ) : null}
        {dispatch.status === "requested" ? (
          <div>
            <p className={stale ? "font-medium text-warning" : "text-muted"}>
              {stale
                ? t("active.stale")
                : t("active.requestedAgo", { minutes: minutesWaiting(dispatch.requested_at) })}
            </p>
          </div>
        ) : null}
        {dispatch.notify_count > 0 ? (
          <div>
            <p className="text-muted">{t("active.notified", { count: dispatch.notify_count })}</p>
          </div>
        ) : null}
        {dispatch.failure_reason ? (
          <div>
            <p className="text-danger">
              {t("active.failureReason", { reason: dispatch.failure_reason })}
            </p>
          </div>
        ) : null}
        {dispatch.delivered_via ? (
          <div>
            <p className="text-success">
              {dispatch.delivered_via === "handover_code"
                ? t("active.deliveredViaCode")
                : t("active.deliveredViaPhoto")}
            </p>
          </div>
        ) : null}
        {dispatch.handover_locked ? (
          <div>
            <p className="text-warning">{t("active.locked")}</p>
          </div>
        ) : null}
        {doorPaymentEnabled && dispatch.door_payment_state ? (
          <div>
            <p
              className={
                dispatch.door_payment_state === "paid" || dispatch.door_payment_state === "cash"
                  ? "text-success"
                  : dispatch.door_payment_state === "exception" ||
                      dispatch.door_payment_state === "failed"
                    ? "text-warning"
                    : "text-muted"
              }
              data-testid="door-payment-state"
            >
              {t(`doorPayment.states.${dispatch.door_payment_state}`)}
            </p>
          </div>
        ) : null}
      </div>

      {flagEnabled && doorPaymentEnabled && doorPaymentActions(dispatch).length > 0 ? (
        <div className="flex flex-wrap gap-2" aria-label={t("doorPayment.title")}>
          {doorPaymentActions(dispatch).map((action) => (
            <button
              key={action}
              type="button"
              className="rounded border border-border px-3 py-1 text-sm"
              disabled={busy}
              onClick={() =>
                void run(
                  `/admin/dispatch/requests/${dispatch.id}/door-payment/${action}`,
                  {},
                  t(`doorPayment.done.${action}`),
                )
              }
            >
              {t(`doorPayment.actions.${action}`)}
            </button>
          ))}
        </div>
      ) : null}

      {flagEnabled && canNotify(dispatch) ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-white disabled:opacity-60"
            disabled={busy}
            onClick={() => void notify("whatsapp")}
          >
            {busy ? t("notify.sending") : t("notify.whatsapp")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm disabled:opacity-60"
            disabled={busy}
            onClick={() => void notify("email")}
          >
            {t("notify.email")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
            onClick={() => void copyMessage()}
          >
            {t("notify.copy")}
          </button>
        </div>
      ) : null}

      {message ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted">{t("notify.messageTitle")}</p>
          <textarea
            readOnly
            className="min-h-32 w-full rounded-md border border-border px-3 py-2 font-mono text-xs"
            value={message.text}
            aria-label={t("notify.messageTitle")}
          />
          {shareUrl ? (
            <a
              href={shareUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
            >
              {t("notify.openWhatsApp")}
            </a>
          ) : null}
        </div>
      ) : null}

      {actions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => (
            <button
              key={action}
              type="button"
              className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
                openAction === action ? "border-primary text-primary" : "border-border text-text"
              }`}
              onClick={() => {
                setError(null);
                setOpenAction(openAction === action ? null : action);
              }}
              data-testid={`dispatch-action-${action}`}
            >
              {t(`actions.${action}`)}
            </button>
          ))}
        </div>
      ) : null}

      {openAction ? (
        <form
          className="space-y-3 rounded-md border border-border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submitAction(openAction);
          }}
        >
          {openAction === "verifyHandover" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("handover.label")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3 font-mono tracking-widest"
                inputMode="numeric"
                autoComplete="off"
                maxLength={6}
                value={code}
                placeholder={t("handover.placeholder")}
                onChange={(change) => setCode(change.target.value.replace(/[^0-9]/g, ""))}
              />
              <span className="block text-xs text-muted">{t("handover.help")}</span>
            </label>
          ) : null}
          {openAction === "accept" || openAction === "pickUp" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("actions.courierRef")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3"
                maxLength={120}
                value={courierRef}
                placeholder={t("actions.courierRefPlaceholder")}
                onChange={(change) => setCourierRef(change.target.value)}
              />
            </label>
          ) : null}
          {openAction === "fail" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("actions.failureReason")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3"
                maxLength={500}
                value={reason}
                placeholder={t("actions.failureReasonPlaceholder")}
                onChange={(change) => setReason(change.target.value)}
              />
            </label>
          ) : null}
          {openAction === "deliverWithPhoto" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("actions.podPublicId")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3 font-mono"
                maxLength={255}
                value={podId}
                placeholder={t("actions.podPlaceholder")}
                onChange={(change) => setPodId(change.target.value)}
              />
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
              disabled={busy}
            >
              {busy
                ? openAction === "verifyHandover"
                  ? t("handover.verifying")
                  : t("actions.working")
                : openAction === "verifyHandover"
                  ? t("handover.submit")
                  : t("actions.confirm")}
            </button>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
              onClick={() => setOpenAction(null)}
            >
              {t("actions.close")}
            </button>
          </div>
        </form>
      ) : null}

      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-success">{notice}</p> : null}
    </li>
  );
}
