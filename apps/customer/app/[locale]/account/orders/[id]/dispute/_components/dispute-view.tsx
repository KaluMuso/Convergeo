"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";

export type DisputePageLabels = {
  title: string;
  body: string;
  holdTrust: string;
  statusLabel: string;
  evidenceLabel: string;
  evidenceHelp: string;
  addEvidence: string;
  uploading: string;
  descriptionLabel: string;
  descriptionPlaceholder: string;
  submit: string;
  submitting: string;
  success: string;
  error: string;
  back: string;
  timelineTitle: string;
  statusOpen: string;
  statusVendorResponded: string;
  statusUnderReview: string;
  statusResolvedRefund: string;
  statusResolvedRelease: string;
  statusResolvedPartial: string;
  statusRejected: string;
};

type DisputeTimelineEntry = {
  from_status: string | null;
  to_status: string;
  note: string | null;
  actor: string | null;
  at: string;
};

type DisputeResponse = {
  id: string;
  order_id: string;
  status: string;
  evidence_paths: string[];
  vendor_response: string | null;
  admin_decision: string | null;
  timeline: DisputeTimelineEntry[];
};

type DisputePageProps = {
  locale: string;
  orderId: string;
  accessToken: string;
  initialDispute: DisputeResponse | null;
  labels: DisputePageLabels;
};

const MAX_EVIDENCE_FILES = 8;
const MAX_EVIDENCE_BYTES = 10_485_760;

const ACCEPTED_EVIDENCE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function statusLabel(status: string, labels: DisputePageLabels): string {
  const map: Record<string, string> = {
    open: labels.statusOpen,
    vendor_responded: labels.statusVendorResponded,
    under_review: labels.statusUnderReview,
    resolved_refund: labels.statusResolvedRefund,
    resolved_release: labels.statusResolvedRelease,
    resolved_partial: labels.statusResolvedPartial,
    rejected: labels.statusRejected,
  };
  return map[status] ?? status;
}

export function DisputePageView({
  locale,
  orderId,
  accessToken,
  initialDispute,
  labels,
}: DisputePageProps) {
  const t = useTranslations("orders.dispute");
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dispute, setDispute] = useState<DisputeResponse | null>(initialDispute);
  const [description, setDescription] = useState("");
  const [evidencePaths, setEvidencePaths] = useState<string[]>(
    initialDispute?.evidence_paths ?? [],
  );
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const canOpen = dispute === null;

  const handleUpload = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || evidencePaths.length >= MAX_EVIDENCE_FILES) {
        return;
      }
      setUploading(true);
      setError(undefined);
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });

      try {
        const newPaths: string[] = [];
        for (const file of Array.from(files)) {
          if (evidencePaths.length + newPaths.length >= MAX_EVIDENCE_FILES) {
            break;
          }
          if (!ACCEPTED_EVIDENCE_TYPES.has(file.type) || file.size > MAX_EVIDENCE_BYTES) {
            continue;
          }
          const sign = await client.request<{
            bucket: string;
            path: string;
            token: string;
            signed_url: string;
          }>(`/orders/${orderId}/evidence/sign`, {
            method: "POST",
            body: JSON.stringify({
              file_size_bytes: file.size,
              content_type: file.type,
            }),
          });
          await fetch(sign.signed_url, {
            method: "PUT",
            headers: { "Content-Type": file.type },
            body: file,
          });
          newPaths.push(sign.path);
        }
        setEvidencePaths((prev) => [...prev, ...newPaths]);
      } catch {
        setError(labels.error);
      } finally {
        setUploading(false);
      }
    },
    [accessToken, evidencePaths.length, labels.error, orderId],
  );

  const handleSubmit = useCallback(async () => {
    if (!canOpen || submitting) {
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const response = await client.request<DisputeResponse>(`/disputes/orders/${orderId}`, {
        method: "POST",
        body: JSON.stringify({
          description,
          evidence_paths: evidencePaths,
        }),
      });
      setDispute(response);
      setSuccess(true);
      router.refresh();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(labels.error);
      } else {
        setError(labels.error);
      }
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, canOpen, description, evidencePaths, labels.error, orderId, router, submitting]);

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link
          href={`/${locale}/account/orders/${orderId}`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
        >
          {labels.back}
        </Link>
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="text-sm text-text-2">{labels.body}</p>
        <p className="rounded border border-border bg-surface px-3 py-2 text-sm text-text-2">
          {labels.holdTrust}
        </p>
      </header>

      {dispute ? (
        <section className="space-y-4 rounded border border-border bg-surface p-4">
          <p className="text-sm font-medium text-display-ink">
            {t("statusDisplay", { status: statusLabel(dispute.status, labels) })}
          </p>
          {dispute.vendor_response ? (
            <p className="text-sm text-text-2">{dispute.vendor_response}</p>
          ) : null}
          {dispute.timeline.length > 0 ? (
            <div className="space-y-2">
              <h3 className="font-display text-h3 text-display-ink">{labels.timelineTitle}</h3>
              <ol className="space-y-2 text-sm text-text-2">
                {dispute.timeline.map((entry) => (
                  <li key={`${entry.at}-${entry.to_status}`}>
                    {statusLabel(entry.to_status, labels)}
                    {entry.note ? t("timelineNote", { note: entry.note }) : null}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </section>
      ) : null}

      {canOpen ? (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <FormField id="dispute-description" label={labels.descriptionLabel}>
            <textarea
              id="dispute-description"
              className="min-h-24 w-full rounded border border-border bg-surface px-3 py-2 text-sm"
              placeholder={labels.descriptionPlaceholder}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </FormField>

          <div className="space-y-2">
            <p className="text-sm font-medium text-display-ink">{labels.evidenceLabel}</p>
            <p className="text-xs text-text-2">{labels.evidenceHelp}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              className="sr-only"
              multiple
              onChange={(event) => void handleUpload(event.target.files)}
            />
            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full"
              disabled={uploading || evidencePaths.length >= MAX_EVIDENCE_FILES}
              loading={uploading}
              loadingLabel={labels.uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {labels.addEvidence}
            </Button>
            {evidencePaths.length > 0 ? (
              <p className="text-xs text-text-2">
                {t("evidenceCount", { count: evidencePaths.length })}
              </p>
            ) : null}
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {success ? <p className="text-sm text-success">{labels.success}</p> : null}

          <Button
            type="submit"
            className="min-h-11 w-full"
            disabled={submitting}
            loading={submitting}
            loadingLabel={labels.submitting}
          >
            {labels.submit}
          </Button>
        </form>
      ) : null}
    </section>
  );
}
