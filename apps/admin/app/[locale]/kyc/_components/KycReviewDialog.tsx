"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type VendorKycDetail, type VendorQueueItem, kycApi } from "./api";
import { DocViewer } from "./DocViewer";

type KycReviewDialogProps = {
  item: VendorQueueItem;
  onClose: () => void;
  onComplete: () => void;
};

export function KycReviewDialog({ item, onClose, onComplete }: KycReviewDialogProps) {
  const t = useTranslations("admin.kyc.queue.dialog");
  const [detail, setDetail] = useState<VendorKycDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "reject">("view");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kycApi.request<VendorKycDetail>(`/admin/vendors/${item.vendor_id}/kyc`);
      setDetail(data);
    } catch {
      setError(t("failure"));
    } finally {
      setLoading(false);
    }
  }, [item.vendor_id, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (action: "approve" | "reject") => {
    if (action === "reject" && reason.trim().length < 3) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await kycApi.request(`/admin/vendors/${item.vendor_id}/status`, {
        method: "PATCH",
        body: JSON.stringify(
          action === "approve"
            ? { action: "approve" }
            : {
                action: "reject",
                reason: reason.trim(),
                reason_template: "other",
              },
        ),
      });
      onComplete();
    } catch {
      setError(t("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="kyc-review-title"
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-4 shadow-lg">
        <h2 id="kyc-review-title" className="font-serif text-lg text-text">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {item.display_name} · {item.slug}
        </p>

        {loading ? <p className="mt-4 text-sm text-muted">{t("submitting")}</p> : null}
        {error ? <p className="mt-4 text-sm text-danger">{error}</p> : null}

        {detail ? (
          <div className="mt-4 space-y-4">
            <section>
              <h3 className="text-sm font-semibold text-text">{t("documents")}</h3>
              <DocViewer documents={detail.documents} docsAvailable={detail.docs_available} />
            </section>

            {mode === "reject" ? (
              <label className="block text-sm text-text">
                {t("rejectReason")}
                <textarea
                  className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
                  rows={3}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder={t("rejectReasonPlaceholder")}
                />
              </label>
            ) : null}

            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={onClose}
                disabled={submitting}
              >
                {t("cancel")}
              </button>
              {mode === "view" ? (
                <>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger"
                    onClick={() => setMode("reject")}
                    disabled={submitting}
                  >
                    {t("reject")}
                  </button>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-white"
                    onClick={() => void submit("approve")}
                    disabled={submitting}
                  >
                    {submitting ? t("submitting") : t("approve")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md bg-danger px-4 text-sm font-medium text-white disabled:opacity-60"
                  onClick={() => void submit("reject")}
                  disabled={submitting || reason.trim().length < 3}
                >
                  {submitting ? t("submitting") : t("reject")}
                </button>
              )}
            </div>
          </div>
        ) : null}

        {!loading && !detail && !error ? (
          <p className="mt-4 text-sm text-muted">{t("noKycRecord")}</p>
        ) : null}
      </div>
    </div>
  );
}
