"use client";

import { formatK } from "@vergeo/i18n";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

type TicketActionsProps = {
  ticketId: string;
  status: "issued" | "checked_in" | "transferred" | "void";
};

type CancelPolicy = {
  band: string;
  refund_ngwee: number;
  cancellable: boolean;
  reschedule_opt_out_open: boolean;
};

async function readAccessToken(): Promise<string | null> {
  const { createBrowserClient } = await import("@vergeo/auth");
  const supabase = createBrowserClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export function TicketActions({ ticketId, status }: TicketActionsProps) {
  const t = useTranslations("events.wallet.detail");
  const locale = useLocale();
  const [busy, setBusy] = useState<"cancel" | "optOut" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [policy, setPolicy] = useState<CancelPolicy | null>(null);

  useEffect(() => {
    if (status !== "issued") {
      return;
    }
    let cancelled = false;
    void (async () => {
      const token = await readAccessToken();
      if (!token || cancelled) {
        return;
      }
      try {
        const response = await fetch(
          `${getApiBaseUrl().replace(/\/$/, "")}/account/tickets/${ticketId}/cancel-policy`,
          { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" } },
        );
        if (!response.ok || cancelled) {
          return;
        }
        const payload = (await response.json()) as CancelPolicy;
        if (!cancelled) {
          setPolicy(payload);
        }
      } catch {
        if (!cancelled) {
          setPolicy(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, ticketId]);

  const postAction = useCallback(
    async (path: "cancel" | "reschedule-opt-out") => {
      setError(null);
      setMessage(null);
      const token = await readAccessToken();
      if (!token) {
        setError(t("cancel.loginRequired"));
        return;
      }
      setBusy(path === "cancel" ? "cancel" : "optOut");
      try {
        const response = await fetch(
          `${getApiBaseUrl().replace(/\/$/, "")}/account/tickets/${ticketId}/${path}`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              Accept: "application/json",
            },
          },
        );
        const payload: unknown = await response.json().catch(() => null);
        if (!response.ok) {
          const code =
            payload &&
            typeof payload === "object" &&
            "error" in payload &&
            typeof (payload as { error?: { code?: string } }).error?.code === "string"
              ? (payload as { error: { code: string } }).error.code
              : null;
          if (code === "ticket_cancel_window_closed" || code === "ticket_unpaid_hold") {
            setError(t("cancel.tooLate"));
            return;
          }
          if (code === "reschedule_opt_out_closed") {
            setError(t("cancel.noReschedule"));
            return;
          }
          setError(t("cancel.failed"));
          return;
        }
        const refund =
          payload &&
          typeof payload === "object" &&
          "refund_ngwee" in payload &&
          typeof (payload as { refund_ngwee?: number }).refund_ngwee === "number"
            ? (payload as { refund_ngwee: number }).refund_ngwee
            : 0;
        const queued =
          payload &&
          typeof payload === "object" &&
          "queued" in payload &&
          Boolean((payload as { queued?: boolean }).queued);
        setMessage(
          queued ? t("cancel.queued", { amount: formatK(refund) }) : t("cancel.voidedNoRefund"),
        );
        window.setTimeout(() => {
          window.location.assign(`/${locale}/account/tickets`);
        }, 1200);
      } catch {
        setError(t("cancel.failed"));
      } finally {
        setBusy(null);
      }
    },
    [locale, t, ticketId],
  );

  if (status !== "issued") {
    return null;
  }

  const showCancel = policy?.cancellable ?? true;
  const showOptOut = policy?.reschedule_opt_out_open ?? false;

  if (!showCancel && !showOptOut && policy) {
    return (
      <section className="space-y-3 rounded border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-display-ink">{t("cancel.heading")}</h3>
        <p className="text-sm text-text-2">{t("cancel.tooLate")}</p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold text-display-ink">{t("cancel.heading")}</h3>
      <p className="text-sm text-text-2">{t("cancel.policy")}</p>
      {policy?.cancellable ? (
        <p className="text-sm text-text">
          {t("cancel.thisRefund", { amount: formatK(policy.refund_ngwee) })}
        </p>
      ) : null}
      <div className="flex flex-col gap-2 sm:flex-row">
        {showCancel ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center justify-center rounded bg-danger px-4 text-sm font-semibold text-surface disabled:opacity-50"
            disabled={busy !== null}
            onClick={() => {
              void postAction("cancel");
            }}
          >
            {busy === "cancel" ? t("cancel.submitting") : t("cancel.cta")}
          </button>
        ) : null}
        {showOptOut ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-sm font-semibold text-text disabled:opacity-50"
            disabled={busy !== null}
            onClick={() => {
              void postAction("reschedule-opt-out");
            }}
          >
            {busy === "optOut" ? t("cancel.submitting") : t("cancel.optOutCta")}
          </button>
        ) : null}
      </div>
      {message ? <p className="text-sm text-success">{message}</p> : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
