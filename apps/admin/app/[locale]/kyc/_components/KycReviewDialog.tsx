"use client";

import { Modal } from "@vergeo/ui/src/modal";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
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
  const locale = useLocale();
  const [detail, setDetail] = useState<VendorKycDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "reject" | "confirmApprove">("view");
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
    <Modal
      open
      onClose={submitting ? () => undefined : onClose}
      title={t("title")}
      closeOnEscape={!submitting}
      closeOnScrimClick={false}
      panelStyle={{ width: "min(100% - 2rem, 44rem)", maxHeight: "92vh" }}
      data-testid="kyc-review-dialog"
    >
      <div className="space-y-4">
        <p className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
          <span>
            {item.display_name} · {item.slug}
          </span>
          {item.kyc_record_id ? (
            <Link
              href={`/${locale}/kyc/${item.kyc_record_id}`}
              className="inline-flex min-h-11 items-center font-medium text-primary underline-offset-2 hover:underline"
            >
              {t("openFullReview")}
            </Link>
          ) : null}
        </p>

        {loading ? (
          <p role="status" className="text-sm text-muted">
            {t("loading")}
          </p>
        ) : null}
        {error ? (
          <div role="alert" className="space-y-2">
            <p className="text-sm text-danger">{error}</p>
            {!detail ? (
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={() => void load()}
              >
                {t("retry")}
              </button>
            ) : null}
          </div>
        ) : null}

        {detail ? (
          <>
            <section aria-label={t("documents")}>
              <h3 className="mb-2 text-sm font-semibold text-text">{t("documents")}</h3>
              <DocViewer
                documents={detail.documents}
                docsAvailable={detail.docs_available}
                onRefresh={() => void load()}
              />
            </section>

            {mode === "reject" ? (
              <div className="space-y-2">
                <label className="block text-sm text-text">
                  {t("rejectReason")}
                  <textarea
                    className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                    rows={3}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder={t("rejectReasonPlaceholder")}
                    required
                    aria-describedby="kyc-reject-hint"
                  />
                </label>
                <p id="kyc-reject-hint" className="text-xs text-muted">
                  {t("rejectVisibleToVendor")}
                </p>
              </div>
            ) : null}

            {mode === "confirmApprove" ? (
              <p className="rounded-md border border-border bg-bg p-3 text-sm text-text">
                {t("confirmApprove", { vendor: item.display_name })}
              </p>
            ) : null}

            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={mode === "view" ? onClose : () => setMode("view")}
                disabled={submitting}
              >
                {mode === "view" ? t("cancel") : t("back")}
              </button>
              {mode === "view" ? (
                <>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger"
                    onClick={() => setMode("reject")}
                  >
                    {t("reject")}
                  </button>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-on-danger"
                    onClick={() => setMode("confirmApprove")}
                  >
                    {t("approve")}
                  </button>
                </>
              ) : mode === "confirmApprove" ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-on-danger disabled:opacity-60"
                  onClick={() => void submit("approve")}
                  disabled={submitting}
                >
                  {submitting ? t("submitting") : t("approveConfirm")}
                </button>
              ) : (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md bg-danger px-4 text-sm font-medium text-on-danger disabled:opacity-60"
                  onClick={() => void submit("reject")}
                  disabled={submitting || reason.trim().length < 3}
                >
                  {submitting ? t("submitting") : t("rejectConfirm")}
                </button>
              )}
            </div>
          </>
        ) : null}

        {!loading && !detail && !error ? (
          <p className="text-sm text-muted">{t("noKycRecord")}</p>
        ) : null}
      </div>
    </Modal>
  );
}
