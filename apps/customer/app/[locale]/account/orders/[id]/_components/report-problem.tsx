"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

export type ReportProblemLabels = {
  title: string;
  body: string;
  categoryLabel: string;
  categoryFaulty: string;
  categoryWrong: string;
  categoryNotDelivered: string;
  categoryOther: string;
  descriptionLabel: string;
  descriptionPlaceholder: string;
  evidenceLabel: string;
  evidenceHelp: string;
  addEvidence: string;
  uploading: string;
  submit: string;
  submitting: string;
  successLane1: string;
  successDispute: string;
  successSupport: string;
  successGuidance: string;
  error: string;
  requiredDescription: string;
};

type ProblemCategory = "faulty" | "wrong" | "not_delivered" | "other";

type ReportProblemBlockProps = {
  orderId: string;
  accessToken: string;
  status: string;
  labels: ReportProblemLabels;
};

type EvidenceSignResponse = {
  bucket: string;
  path: string;
  token: string;
  signed_url: string;
};

type ReportResponse = {
  order_id: string;
  route: "lane1" | "dispute" | "support" | "guidance";
  within_window: boolean;
  dispute_id?: string | null;
  guidance_key?: string | null;
};

const PRIVATE_EVIDENCE_BUCKET = "order-evidence";
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

function successMessage(route: ReportResponse["route"], labels: ReportProblemLabels): string {
  switch (route) {
    case "lane1":
      return labels.successLane1;
    case "dispute":
      return labels.successDispute;
    case "support":
      return labels.successSupport;
    case "guidance":
      return labels.successGuidance;
    default:
      return labels.successSupport;
  }
}

export function ReportProblemBlock({
  orderId,
  accessToken,
  status,
  labels,
}: ReportProblemBlockProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState<ProblemCategory>("faulty");
  const [description, setDescription] = useState("");
  const [evidencePaths, setEvidencePaths] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [successText, setSuccessText] = useState<string | undefined>();
  const [descriptionError, setDescriptionError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | undefined>();

  const reportableStatuses = new Set(["shipped", "delivered", "completed"]);
  const canReport = reportableStatuses.has(status) && !submitted;

  const uploadEvidence = useCallback(
    async (file: File) => {
      if (!ACCEPTED_EVIDENCE_TYPES.has(file.type)) {
        setFormError(labels.error);
        return;
      }
      if (file.size > MAX_EVIDENCE_BYTES) {
        setFormError(labels.error);
        return;
      }
      if (evidencePaths.length >= MAX_EVIDENCE_FILES) {
        return;
      }

      setUploading(true);
      setFormError(undefined);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => accessToken,
        });
        const signed = await client.request<EvidenceSignResponse>(
          `/orders/${orderId}/evidence/sign`,
          {
            method: "POST",
            body: JSON.stringify({
              file_size_bytes: file.size,
              content_type: file.type,
            }),
          },
        );
        if (signed.bucket !== PRIVATE_EVIDENCE_BUCKET) {
          throw new Error("Evidence must use the private bucket");
        }

        const headers = new Headers();
        headers.set("Content-Type", file.type);
        const uploadResponse = await fetch(signed.signed_url, {
          method: "PUT",
          headers,
          body: file,
        });
        if (!uploadResponse.ok) {
          throw new Error("Upload failed");
        }
        setEvidencePaths((current) => [...current, signed.path]);
      } catch {
        setFormError(labels.error);
      } finally {
        setUploading(false);
      }
    },
    [accessToken, evidencePaths.length, labels.error, orderId],
  );

  const handleSubmit = useCallback(async () => {
    if (!canReport || submitting) {
      return;
    }
    const trimmed = description.trim();
    if (!trimmed) {
      setDescriptionError(labels.requiredDescription);
      return;
    }
    setDescriptionError(undefined);
    setFormError(undefined);
    setSubmitting(true);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const response = await client.request<ReportResponse>(`/orders/${orderId}/report-problem`, {
        method: "POST",
        body: JSON.stringify({
          category,
          description: trimmed,
          evidence_paths: evidencePaths,
        }),
      });
      setSubmitted(true);
      setSuccessText(successMessage(response.route, labels));
      router.refresh();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setFormError(labels.error);
      } else {
        setFormError(labels.error);
      }
    } finally {
      setSubmitting(false);
    }
  }, [
    accessToken,
    canReport,
    category,
    description,
    evidencePaths,
    labels,
    orderId,
    router,
    submitting,
  ]);

  if (!reportableStatuses.has(status)) {
    return null;
  }

  return (
    <section
      aria-labelledby="report-problem-heading"
      className="space-y-4 rounded border border-border bg-surface p-4"
    >
      <div className="space-y-1">
        <h3 id="report-problem-heading" className="font-display text-h3 text-display-ink">
          {labels.title}
        </h3>
        <p className="text-sm text-text-2">{labels.body}</p>
      </div>

      {submitted && successText ? (
        <p className="text-sm font-medium text-display-ink" role="status">
          {successText}
        </p>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <FormField id="problem-category" label={labels.categoryLabel}>
            <select
              className="min-h-11 w-full rounded border border-border bg-bg px-3 text-sm text-display-ink"
              value={category}
              disabled={!canReport || submitting}
              onChange={(event) => setCategory(event.target.value as ProblemCategory)}
            >
              <option value="faulty">{labels.categoryFaulty}</option>
              <option value="wrong">{labels.categoryWrong}</option>
              <option value="not_delivered">{labels.categoryNotDelivered}</option>
              <option value="other">{labels.categoryOther}</option>
            </select>
          </FormField>

          <FormField
            id="problem-description"
            label={labels.descriptionLabel}
            errorMessage={descriptionError}
          >
            <textarea
              className="min-h-24 w-full rounded border border-border bg-bg px-3 py-2 text-sm text-display-ink"
              placeholder={labels.descriptionPlaceholder}
              value={description}
              disabled={!canReport || submitting}
              onChange={(event) => setDescription(event.target.value)}
            />
          </FormField>

          <div className="space-y-2">
            <p className="text-sm font-medium text-display-ink">{labels.evidenceLabel}</p>
            <p className="text-sm text-text-2">{labels.evidenceHelp}</p>
            {evidencePaths.length > 0 ? (
              <ul className="space-y-1 text-xs text-text-2">
                {evidencePaths.map((path) => (
                  <li key={path} className="truncate font-mono">
                    {path.split("/").pop()}
                  </li>
                ))}
              </ul>
            ) : null}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              className="sr-only"
              disabled={!canReport || uploading || submitting}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) {
                  void uploadEvidence(file);
                }
              }}
            />
            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full"
              disabled={
                !canReport || uploading || submitting || evidencePaths.length >= MAX_EVIDENCE_FILES
              }
              loading={uploading}
              loadingLabel={labels.uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {labels.addEvidence}
            </Button>
          </div>

          {formError ? (
            <p className="text-sm text-error" role="alert">
              {formError}
            </p>
          ) : null}

          <Button
            type="submit"
            className="min-h-11 w-full"
            disabled={!canReport || submitting}
            loading={submitting}
            loadingLabel={labels.submitting}
          >
            {labels.submit}
          </Button>
        </form>
      )}
    </section>
  );
}
