"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

export type ReturnFormLabels = {
  title: string;
  body: string;
  lane1Title: string;
  lane1Body: string;
  lane2Title: string;
  lane2Unavailable: string;
  evidenceLabel: string;
  evidenceHelp: string;
  addEvidence: string;
  uploading: string;
  breakdownTitle: string;
  breakdownItem: string;
  breakdownDelivery: string;
  breakdownTotal: string;
  windowExpired: string;
  submit: string;
  submitting: string;
  success: string;
  error: string;
  evidenceRequired: string;
};

type ReturnPreview = {
  lane: number;
  order_item_id: string;
  order_id: string;
  within_window: boolean;
  fee_breakdown: {
    item_ngwee?: number;
    delivery_ngwee?: number;
    total_ngwee?: number;
  };
  lane2_eligible?: boolean;
  lane2_reason?: string | null;
};

type SubmitReturnResponse = {
  id: string;
  order_item_id: string;
  lane: number;
  status: string;
  fee_breakdown: Record<string, unknown>;
};

type EvidenceSignResponse = {
  bucket: string;
  path: string;
  token: string;
  signed_url: string;
};

type ReturnFormProps = {
  orderId: string;
  orderItemId: string;
  accessToken: string;
  labels: ReturnFormLabels;
};

const PRIVATE_EVIDENCE_BUCKET = "order-evidence";
const MAX_EVIDENCE_FILES = 8;
const MAX_EVIDENCE_BYTES = 10_485_760;

const ACCEPTED_EVIDENCE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function ReturnForm({ orderId, orderItemId, accessToken, labels }: ReturnFormProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [evidencePaths, setEvidencePaths] = useState<string[]>([]);
  const [preview, setPreview] = useState<ReturnPreview | null>(null);
  const [lane2Preview, setLane2Preview] = useState<ReturnPreview | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | undefined>();
  const [evidenceError, setEvidenceError] = useState<string | undefined>();

  const apiClient = createApiClient({
    baseUrl: getApiBaseUrl(),
    getToken: () => accessToken,
  });

  useEffect(() => {
    let cancelled = false;
    async function loadPreview() {
      try {
        const lane1 = await apiClient.request<ReturnPreview>(
          `/returns/preview?order_item_id=${encodeURIComponent(orderItemId)}&lane=1`,
        );
        if (!cancelled) {
          setPreview(lane1);
        }
        try {
          const lane2 = await apiClient.request<ReturnPreview>(
            `/returns/preview?order_item_id=${encodeURIComponent(orderItemId)}&lane=2`,
          );
          if (!cancelled) {
            setLane2Preview(lane2);
          }
        } catch {
          if (!cancelled) {
            setLane2Preview(null);
          }
        }
      } catch {
        if (!cancelled) {
          setFormError(labels.error);
        }
      }
    }
    void loadPreview();
    return () => {
      cancelled = true;
    };
  }, [apiClient, labels.error, orderItemId]);

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
        const signed = await apiClient.request<EvidenceSignResponse>(
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
        setEvidenceError(undefined);
      } catch {
        setFormError(labels.error);
      } finally {
        setUploading(false);
      }
    },
    [apiClient, evidencePaths.length, labels.error, orderId],
  );

  const handleSubmit = useCallback(async () => {
    if (submitting || submitted) {
      return;
    }
    if (evidencePaths.length < 1) {
      setEvidenceError(labels.evidenceRequired);
      return;
    }
    if (!preview?.within_window) {
      setFormError(labels.windowExpired);
      return;
    }

    setEvidenceError(undefined);
    setFormError(undefined);
    setSubmitting(true);
    try {
      await apiClient.request<SubmitReturnResponse>("/returns", {
        method: "POST",
        body: JSON.stringify({
          order_item_id: orderItemId,
          lane: 1,
          evidence_paths: evidencePaths,
        }),
      });
      setSubmitted(true);
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
    apiClient,
    evidencePaths,
    labels,
    orderItemId,
    preview?.within_window,
    router,
    submitted,
    submitting,
  ]);

  const canSubmit =
    !submitted && preview?.within_window === true && evidencePaths.length >= 1 && !submitting;

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="text-sm text-text-2">{labels.body}</p>
      </div>

      <div className="space-y-2 rounded border border-border bg-surface p-4">
        <h3 className="font-display text-h3 text-display-ink">{labels.lane1Title}</h3>
        <p className="text-sm text-text-2">{labels.lane1Body}</p>
        {preview && preview.within_window && preview.fee_breakdown ? (
          <dl className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
            <p className="font-medium text-display-ink">{labels.breakdownTitle}</p>
            <div className="flex justify-between gap-3">
              <dt className="text-text-2">{labels.breakdownItem}</dt>
              <dd className="font-mono text-display-ink">
                {formatK(preview.fee_breakdown.item_ngwee ?? 0)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-text-2">{labels.breakdownDelivery}</dt>
              <dd className="font-mono text-display-ink">
                {formatK(preview.fee_breakdown.delivery_ngwee ?? 0)}
              </dd>
            </div>
            <div className="flex justify-between gap-3 font-medium">
              <dt className="text-display-ink">{labels.breakdownTotal}</dt>
              <dd className="font-mono text-display-ink">
                {formatK(preview.fee_breakdown.total_ngwee ?? 0)}
              </dd>
            </div>
          </dl>
        ) : preview && !preview.within_window ? (
          <p className="text-sm text-error" role="alert">
            {labels.windowExpired}
          </p>
        ) : null}
      </div>

      {lane2Preview?.lane2_eligible ? (
        <div className="rounded border border-border bg-surface p-4">
          <h3 className="font-display text-h3 text-display-ink">{labels.lane2Title}</h3>
          <p className="mt-1 text-sm text-text-2">
            {formatK((lane2Preview.fee_breakdown as { refund_ngwee?: number }).refund_ngwee ?? 0)}
          </p>
        </div>
      ) : (
        <p className="text-xs text-text-2">{labels.lane2Unavailable}</p>
      )}

      {submitted ? (
        <p className="text-sm font-medium text-display-ink" role="status">
          {labels.success}
        </p>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
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
            {evidenceError ? (
              <p className="text-sm text-error" role="alert">
                {evidenceError}
              </p>
            ) : null}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              disabled={uploading || submitting || !preview?.within_window}
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
                uploading ||
                submitting ||
                !preview?.within_window ||
                evidencePaths.length >= MAX_EVIDENCE_FILES
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
            disabled={!canSubmit}
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
