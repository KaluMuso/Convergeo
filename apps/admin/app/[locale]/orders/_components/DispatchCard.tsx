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
  FAILURE_CODES,
  type FailureCode,
  isHandoverCodeWellFormed,
  isPodPublicIdWellFormed,
  isStale,
  kwachaTextToNgwee,
  minutesWaiting,
  ngweeToKwachaText,
  targetStatusFor,
  whatsAppShareUrl,
} from "./dispatch-board-model";

type DispatchCardProps = {
  dispatch: Dispatch;
  flagEnabled: boolean;
  onChanged: () => void;
};

type MessageState = { text: string; whatsappTo: string | null } | null;

export function DispatchCard({ dispatch, flagEnabled, onChanged }: DispatchCardProps) {
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
  const [failureCode, setFailureCode] = useState<FailureCode>("customer_unavailable");
  const [cashText, setCashText] = useState(ngweeToKwachaText(dispatch.cod_amount_ngwee || null));
  const [cashMethod, setCashMethod] = useState<"cash" | "mobile_money">("cash");
  const [costText, setCostText] = useState(ngweeToKwachaText(dispatch.actual_cost_ngwee ?? null));

  const actions = flagEnabled ? actionsFor(dispatch) : [];
  const stale = isStale(dispatch);

  const fail = (err: unknown) => {
    const known: Record<string, string> = {
      dispatch_cod_required: "errors.codRequired",
      dispatch_cod_mismatch: "errors.codMismatch",
      dispatch_cod_not_expected: "errors.codNotExpected",
      dispatch_cost_not_allowed: "errors.costNotAllowed",
      order_refund_path_required: "errors.refundPathRequired",
      dispatch_handover_invalid: "errors.handoverInvalidShort",
      dispatch_handover_locked: "errors.handoverLockedShort",
    };
    if (err instanceof ApiError && known[err.code]) {
      setError(t(known[err.code] as string));
      return;
    }
    if (err instanceof ApiError && err.code === "dispatch_invalid_transition") {
      setError(t("errors.invalidTransition"));
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
    if (action === "complete") {
      const proofIsCode = code.trim().length > 0;
      if (proofIsCode && !isHandoverCodeWellFormed(code)) {
        setError(t("errors.codeFormat"));
        return;
      }
      if (!proofIsCode && !isPodPublicIdWellFormed(podId)) {
        setError(t("errors.podFormat"));
        return;
      }
      const cash = dispatch.cod_amount_ngwee > 0 ? kwachaTextToNgwee(cashText) : null;
      if (dispatch.cod_amount_ngwee > 0 && (cash === null || Number.isNaN(cash))) {
        setError(t("errors.codRequired"));
        return;
      }
      await run(
        `/admin/dispatch/requests/${dispatch.id}/complete`,
        {
          handover_code: proofIsCode ? code.trim() : null,
          pod_photo_public_id: proofIsCode ? null : podId.trim(),
          cod_collected_ngwee: cash,
          cod_collected_method: dispatch.cod_amount_ngwee > 0 ? cashMethod : null,
        },
        t("complete.success"),
      );
      setCode("");
      return;
    }
    if (action === "returned") {
      await run(
        `/admin/dispatch/requests/${dispatch.id}/returned`,
        { note: reason.trim() || null },
        t("returned.success"),
      );
      return;
    }
    if (action === "recordCost") {
      const cost = kwachaTextToNgwee(costText);
      if (cost === null || Number.isNaN(cost)) {
        setError(t("errors.costFormat"));
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await ordersApi.request(`/admin/dispatch/requests/${dispatch.id}/cost`, {
          method: "PATCH",
          body: JSON.stringify({ actual_cost_ngwee: cost }),
        });
        setOpenAction(null);
        setNotice(t("cost.success"));
        onChanged();
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
      return;
    }
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
      failure_code: action === "fail" ? failureCode : null,
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
        {dispatch.direction === "return" || (dispatch.attempt_no ?? 1) > 1 ? (
          <div>
            <p className="font-medium text-warning">
              {dispatch.direction === "return"
                ? t("active.returnJob")
                : t("active.attempt", { attempt: dispatch.attempt_no ?? 1 })}
            </p>
          </div>
        ) : null}
        {dispatch.cod_collected_ngwee != null ? (
          <div>
            <p className={dispatch.remitted ? "text-success" : "text-warning"}>
              {dispatch.remitted
                ? t("active.cashRemitted", { amount: formatK(dispatch.cod_collected_ngwee) })
                : t("active.cashHeld", { amount: formatK(dispatch.cod_collected_ngwee) })}
            </p>
          </div>
        ) : null}
        {dispatch.actual_cost_ngwee != null ? (
          <div>
            <p className="text-muted">
              {t("active.actualCost", { amount: formatK(dispatch.actual_cost_ngwee) })}
            </p>
          </div>
        ) : null}
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
      </div>

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
          {openAction === "complete" ? (
            <div className="space-y-3">
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
                <span className="block text-xs text-muted">{t("complete.proofHelp")}</span>
              </label>
              {code.trim().length === 0 ? (
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
              {dispatch.cod_amount_ngwee > 0 ? (
                <div className="flex flex-wrap gap-2">
                  <label className="block flex-1 space-y-1 text-sm">
                    <span className="text-muted">
                      {t("complete.cashLabel", { amount: formatK(dispatch.cod_amount_ngwee) })}
                    </span>
                    <input
                      className="min-h-11 w-full rounded-md border border-border px-3 font-mono"
                      inputMode="decimal"
                      value={cashText}
                      onChange={(change) => setCashText(change.target.value)}
                    />
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted">{t("complete.methodLabel")}</span>
                    <select
                      className="min-h-11 w-full rounded-md border border-border px-3"
                      value={cashMethod}
                      onChange={(change) =>
                        setCashMethod(
                          change.target.value === "mobile_money" ? "mobile_money" : "cash",
                        )
                      }
                    >
                      <option value="cash">{t("complete.methodCash")}</option>
                      <option value="mobile_money">{t("complete.methodMobileMoney")}</option>
                    </select>
                  </label>
                </div>
              ) : (
                <p className="text-xs text-muted">{t("complete.prepaidHelp")}</p>
              )}
            </div>
          ) : null}
          {openAction === "returned" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("returned.noteLabel")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3"
                maxLength={500}
                value={reason}
                placeholder={t("returned.notePlaceholder")}
                onChange={(change) => setReason(change.target.value)}
              />
              <span className="block text-xs text-muted">{t("returned.help")}</span>
            </label>
          ) : null}
          {openAction === "recordCost" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("cost.label")}</span>
              <input
                className="min-h-11 w-full rounded-md border border-border px-3 font-mono"
                inputMode="decimal"
                value={costText}
                placeholder={t("cost.placeholder")}
                onChange={(change) => setCostText(change.target.value)}
              />
            </label>
          ) : null}
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
              <span className="text-muted">{t("actions.failureCode")}</span>
              <select
                className="min-h-11 w-full rounded-md border border-border px-3"
                value={failureCode}
                onChange={(change) => {
                  const next = FAILURE_CODES.find((value) => value === change.target.value);
                  if (next) setFailureCode(next);
                }}
              >
                {FAILURE_CODES.map((value) => (
                  <option key={value} value={value}>
                    {t(`failureCodes.${value}`)}
                  </option>
                ))}
              </select>
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
