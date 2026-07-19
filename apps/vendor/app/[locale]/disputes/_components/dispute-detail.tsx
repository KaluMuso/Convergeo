"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { Button, FormField, Spinner } from "../../listings/new/_lib/ui";

type DisputeDetail = {
  id: string;
  order_id: string;
  status: string;
  evidence_paths: string[];
  vendor_response: string | null;
};

const MAX_EVIDENCE_FILES = 8;
const MAX_EVIDENCE_BYTES = 10_485_760;
const ACCEPTED_EVIDENCE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);

type VendorDisputeDetailViewProps = {
  disputeId: string;
};

export function VendorDisputeDetailView({ disputeId }: VendorDisputeDetailViewProps) {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dispute, setDispute] = useState<DisputeDetail | null>(null);
  const [responseText, setResponseText] = useState("");
  const [evidencePaths, setEvidencePaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session?.access_token ?? null,
      }),
    [session?.access_token],
  );

  const load = useCallback(async () => {
    if (!session?.access_token) {
      return;
    }
    setLoading(true);
    try {
      const row = await client.request<DisputeDetail>(`/disputes/${disputeId}`);
      setDispute(row);
      if (row.vendor_response) {
        setResponseText(row.vendor_response);
      }
    } catch {
      setError(t("disputes.detail.error"));
    } finally {
      setLoading(false);
    }
  }, [client, disputeId, session?.access_token, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const canRespond = dispute?.status === "open";

  const handleUpload = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || !dispute || evidencePaths.length >= MAX_EVIDENCE_FILES) {
        return;
      }
      setUploading(true);
      try {
        const newPaths: string[] = [];
        for (const file of Array.from(files)) {
          if (!ACCEPTED_EVIDENCE_TYPES.has(file.type) || file.size > MAX_EVIDENCE_BYTES) {
            continue;
          }
          const sign = await client.request<{
            signed_url: string;
            path: string;
          }>(`/disputes/vendor/orders/${dispute.order_id}/evidence/sign`, {
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
        setError(t("disputes.detail.error"));
      } finally {
        setUploading(false);
      }
    },
    [client, dispute, evidencePaths.length, t],
  );

  const handleSubmit = useCallback(async () => {
    if (!canRespond || submitting || !responseText.trim()) {
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      const row = await client.request<DisputeDetail>(`/disputes/${disputeId}/respond`, {
        method: "POST",
        body: JSON.stringify({
          response_text: responseText,
          evidence_paths: evidencePaths,
        }),
      });
      setDispute(row);
      setSuccess(true);
    } catch {
      setError(t("disputes.detail.error"));
    } finally {
      setSubmitting(false);
    }
  }, [canRespond, client, disputeId, evidencePaths, responseText, submitting, t]);

  if (loading) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("disputes.detail.title")} />
      </div>
    );
  }

  if (!dispute) {
    return <p className="text-sm text-danger">{error ?? t("disputes.detail.error")}</p>;
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link href="../disputes" className="inline-flex min-h-11 items-center text-sm text-primary">
          {t("disputes.detail.back")}
        </Link>
        <h1 className="font-display text-h2 text-display-ink">{t("disputes.detail.title")}</h1>
        <p className="text-sm text-text-2">
          {t("disputes.detail.order", {
            orderId: dispute.order_id.slice(0, 8).toUpperCase(),
          })}
        </p>
        <p className="text-sm font-medium text-display-ink">
          {t("disputes.detail.statusDisplay", {
            status: t(`disputes.detail.status.${dispute.status}` as "disputes.detail.status.open"),
          })}
        </p>
      </header>

      {dispute.evidence_paths.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-display-ink">
            {t("disputes.detail.customerEvidence")}
          </h2>
          <p className="text-xs text-text-2">
            {t("disputes.detail.evidenceCount", { count: dispute.evidence_paths.length })}
          </p>
        </section>
      ) : null}

      {canRespond ? (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <FormField id="vendor-response" label={t("disputes.detail.responseLabel")}>
            <textarea
              id="vendor-response"
              className="min-h-24 w-full rounded border border-border bg-surface px-3 py-2 text-sm"
              placeholder={t("disputes.detail.responsePlaceholder")}
              value={responseText}
              onChange={(event) => setResponseText(event.target.value)}
            />
          </FormField>

          <div className="space-y-2">
            <p className="text-sm font-medium text-display-ink">
              {t("disputes.detail.evidenceLabel")}
            </p>
            <p className="text-xs text-text-2">{t("disputes.detail.evidenceHelp")}</p>
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
              disabled={uploading}
              loading={uploading}
              loadingLabel={t("disputes.detail.uploading")}
              onClick={() => fileInputRef.current?.click()}
            >
              {t("disputes.detail.addEvidence")}
            </Button>
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {success ? <p className="text-sm text-success">{t("disputes.detail.success")}</p> : null}

          <Button
            type="submit"
            className="min-h-11 w-full"
            disabled={submitting}
            loading={submitting}
            loadingLabel={t("disputes.detail.submitting")}
          >
            {t("disputes.detail.submit")}
          </Button>
        </form>
      ) : (
        <p className="text-sm text-text-2">{t("disputes.detail.alreadyResponded")}</p>
      )}
    </section>
  );
}
