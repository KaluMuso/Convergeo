"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { formatK } from "@vergeo/i18n";
import { glassClass } from "@vergeo/ui/src/glass";
import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { decisionFailureReference, withDecisionRetry } from "../../../../../lib/decision-retry";
import { AdminLoadFailure } from "../../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../../_components/queue-load-failure";

import {
  type CanonicalQueueItem,
  listPendingCanonicalProducts,
  patchCanonicalProductStatus,
} from "./api";

type PendingCanonicalQueueProps = {
  locale: string;
};

export function PendingCanonicalQueue({ locale }: PendingCanonicalQueueProps) {
  const t = useTranslations("admin.moderation.canonical");
  const [items, setItems] = useState<CanonicalQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [selected, setSelected] = useState<CanonicalQueueItem | null>(null);
  const [mode, setMode] = useState<"view" | "reject">("view");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionHint, setActionHint] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  // A ref, not state: two fast clicks land before React re-renders with `submitting`.
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const data = await listPendingCanonicalProducts();
      setItems(data);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const closeDialog = () => {
    setSelected(null);
    setMode("view");
    setReason("");
    setActionError(null);
    setActionHint(null);
  };

  const decide = async (
    item: CanonicalQueueItem,
    status: "active" | "rejected",
    rejectReasonText?: string,
  ) => {
    setSelected(item);
    const effectiveReason = rejectReasonText ?? reason;
    if (status === "rejected" && effectiveReason.trim().length < 3) {
      return;
    }
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    setActionError(null);
    setActionHint(null);
    try {
      // The decision is idempotent server-side, so one automatic retry (after forcing a
      // fresh session token) is safe and hides a stale-token or dropped first request.
      await withDecisionRetry(
        () =>
          patchCanonicalProductStatus(item.id, {
            status,
            reason: status === "rejected" ? effectiveReason.trim() : null,
          }),
        {
          beforeRetry: async () => {
            const client = await getBrowserClient();
            await client.auth.refreshSession();
          },
        },
      );
      closeDialog();
      setMessage(t("dialog.success"));
      notify.success(t("dialog.success"));
      await load();
    } catch (err) {
      setActionError(t("dialog.failure"));
      const reference = decisionFailureReference(err);
      setActionHint(
        [
          t("dialog.failureRetryHint"),
          reference ? t("dialog.failureReference", { id: reference }) : null,
        ]
          .filter(Boolean)
          .join(" "),
      );
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const submit = async (status: "active" | "rejected") => {
    if (!selected) return;
    await decide(selected, status);
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        hint={permissionDenied ? t("permissionDeniedHint") : undefined}
        retryLabel={t("retry")}
        onRetry={() => void load()}
      />
    );
  }

  return (
    <section id="canonical" className="space-y-3 scroll-mt-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-text">{t("title")}</h2>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      {message ? <p className="text-sm text-success">{message}</p> : null}

      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-3 font-medium">{t("product")}</th>
                <th className="px-2 py-3 font-medium">{t("vendor")}</th>
                <th className="px-2 py-3 font-medium">{t("price")}</th>
                <th className="px-2 py-3 font-medium">{t("submitted")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-bg-2">
                  <td className="px-2 py-3">
                    <div className="flex items-center gap-2">
                      {item.image_urls[0] ? (
                        <img
                          src={item.image_urls[0]}
                          alt=""
                          className="size-12 rounded-md border border-border object-cover"
                        />
                      ) : null}
                      <div>
                        <div className="font-medium text-text">{item.name}</div>
                        <div className="text-xs text-muted">{item.slug}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-3 text-muted">{item.vendor_display_name ?? "—"}</td>
                  <td className="px-2 py-3 text-muted">
                    {typeof item.price_ngwee === "number"
                      ? formatK(item.price_ngwee, { locale })
                      : "—"}
                  </td>
                  <td className="px-2 py-3 text-muted">
                    {new Date(item.updated_at).toLocaleString(locale)}
                  </td>
                  <td className="px-2 py-3">
                    <div className="flex flex-col items-end gap-2">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          disabled={submitting}
                          className="inline-flex min-h-11 items-center rounded-md bg-success px-3 text-sm font-medium text-on-danger"
                          onClick={() => void decide(item, "active")}
                        >
                          {t("approve")}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-11 items-center rounded-md border border-danger px-3 text-sm font-medium text-danger"
                          onClick={() => {
                            setRejectingId(rejectingId === item.id ? null : item.id);
                            setRejectReason("");
                          }}
                        >
                          {t("reject")}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-11 items-center rounded-md border border-primary px-3 text-sm font-medium text-primary"
                          onClick={() => {
                            setSelected(item);
                            setMode("view");
                            setReason("");
                            setActionError(null);
                          }}
                        >
                          {t("review")}
                        </button>
                      </div>
                      {rejectingId === item.id ? (
                        <div className="w-full max-w-xs space-y-2 text-left">
                          <label className="block text-xs text-muted">
                            {t("rejectReasonShort")}
                            <textarea
                              className="mt-1 w-full rounded-md border border-border px-2 py-1 text-sm"
                              rows={2}
                              value={rejectReason}
                              onChange={(event) => setRejectReason(event.target.value)}
                            />
                          </label>
                          <button
                            type="button"
                            disabled={submitting || rejectReason.trim().length < 3}
                            className="inline-flex min-h-11 items-center rounded-md bg-danger px-3 text-sm font-medium text-on-danger disabled:opacity-60"
                            onClick={() => {
                              void decide(item, "rejected", rejectReason);
                              setRejectingId(null);
                            }}
                          >
                            {t("dialog.reject")}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 backdrop-blur-[2px] sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="canonical-review-title"
        >
          <div
            className={`${glassClass("overlay")} max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg p-4`}
          >
            <h3 id="canonical-review-title" className="font-serif text-lg text-text">
              {t("dialog.title")}
            </h3>
            <p className="mt-1 text-sm text-muted">
              {selected.name} · {selected.slug}
            </p>

            <section className="mt-4 space-y-2">
              <h4 className="text-sm font-semibold text-text">{t("dialog.images")}</h4>
              {selected.image_urls.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {selected.image_urls.map((url) => (
                    <img
                      key={url}
                      alt={selected.name}
                      className="max-h-64 w-full rounded-md border border-border object-contain bg-bg"
                      src={url}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">{t("dialog.noImages")}</p>
              )}
            </section>

            <CanonicalSubmissionDetails item={selected} heading={t("dialog.details")} />

            {mode === "reject" ? (
              <label className="mt-4 block text-sm text-text">
                {t("dialog.rejectReason")}
                <textarea
                  className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
                  rows={3}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder={t("dialog.rejectReasonPlaceholder")}
                />
              </label>
            ) : null}

            {actionError ? (
              <div className="mt-2 space-y-0.5" role="alert">
                <p className="text-sm text-danger">{actionError}</p>
                {actionHint ? <p className="text-xs text-muted">{actionHint}</p> : null}
              </div>
            ) : null}

            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={closeDialog}
                disabled={submitting}
              >
                {t("dialog.cancel")}
              </button>
              {mode === "view" ? (
                <>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger"
                    onClick={() => setMode("reject")}
                    disabled={submitting}
                  >
                    {t("dialog.reject")}
                  </button>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-white"
                    onClick={() => void submit("active")}
                    disabled={submitting}
                  >
                    {submitting ? t("dialog.submitting") : t("dialog.approve")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md bg-danger px-4 text-sm font-medium text-white disabled:opacity-60"
                  onClick={() => void submit("rejected")}
                  disabled={submitting || reason.trim().length < 3}
                >
                  {submitting ? t("dialog.submitting") : t("dialog.reject")}
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** Submitted content is plain text, including guide text and structured JSON. */
export function CanonicalSubmissionDetails({
  item,
  heading,
}: {
  item: Pick<CanonicalQueueItem, "brand" | "description" | "spec">;
  heading: string;
}) {
  return (
    <section className="mt-4 space-y-2" aria-label={heading}>
      <h4 className="font-medium">{heading}</h4>
      {item.brand ? <p className="break-words">{item.brand}</p> : null}
      {item.description ? (
        <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {item.description}
        </p>
      ) : null}
      {Object.keys(item.spec ?? {}).length ? (
        <pre className="whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]">
          {JSON.stringify(item.spec, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}
