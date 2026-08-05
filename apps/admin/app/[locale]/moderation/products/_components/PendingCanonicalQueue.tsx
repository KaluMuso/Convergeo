"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

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
  };

  const submit = async (status: "active" | "rejected") => {
    if (!selected) {
      return;
    }
    if (status === "rejected" && reason.trim().length < 3) {
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      await patchCanonicalProductStatus(selected.id, {
        status,
        reason: status === "rejected" ? reason.trim() : null,
      });
      closeDialog();
      setMessage(t("dialog.success"));
      await load();
    } catch {
      setActionError(t("dialog.failure"));
    } finally {
      setSubmitting(false);
    }
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
                <th className="px-2 py-3 font-medium">{t("submitted")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-bg-2">
                  <td className="px-2 py-3">
                    <div className="font-medium text-text">{item.name}</div>
                    <div className="text-xs text-muted">{item.slug}</div>
                  </td>
                  <td className="px-2 py-3 text-muted">{item.vendor_display_name ?? "—"}</td>
                  <td className="px-2 py-3 text-muted">
                    {new Date(item.updated_at).toLocaleString(locale)}
                  </td>
                  <td className="px-2 py-3 text-right">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                      onClick={() => {
                        setSelected(item);
                        setMode("view");
                        setReason("");
                        setActionError(null);
                      }}
                    >
                      {t("review")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="canonical-review-title"
        >
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-4 shadow-lg">
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

            {actionError ? <p className="mt-2 text-sm text-danger">{actionError}</p> : null}

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
