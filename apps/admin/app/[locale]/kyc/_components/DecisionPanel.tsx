"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type KycDetail, type RejectReasonTemplate, kycApi } from "./api";

type DecisionPanelProps = {
  detail: KycDetail;
  onDecided: () => void;
};

type DecisionMode = "approve" | "reject" | "resubmit" | "start_review" | "suspend" | "revoke";

const REASON_TEMPLATES: RejectReasonTemplate[] = [
  "blurry_document",
  "name_mismatch",
  "expired_id",
  "incomplete_submission",
  "other",
];

export function DecisionPanel({ detail, onDecided }: DecisionPanelProps) {
  const td = useTranslations("admin.kyc.detail");
  const tr = useTranslations("admin.kyc.reasons");
  const [mode, setMode] = useState<DecisionMode | null>(null);
  const [reasonTemplate, setReasonTemplate] = useState<RejectReasonTemplate>("blurry_document");
  const [freeText, setFreeText] = useState("");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [lifecycleReason, setLifecycleReason] = useState("");
  const [docsRequested, setDocsRequested] = useState<Array<"nrc" | "selfie">>(["nrc", "selfie"]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reviewable = detail.status === "submitted" || detail.status === "under_review";
  const approved = detail.status === "approved";
  const suspended = detail.status === "suspended";

  const toggleDoc = (doc: "nrc" | "selfie") => {
    setDocsRequested((current) =>
      current.includes(doc) ? current.filter((item) => item !== doc) : [...current, doc],
    );
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "start_review") {
        await kycApi.request(`/admin/kyc/${detail.id}/start-review`, {
          method: "POST",
          body: JSON.stringify({ lifecycle_reason: lifecycleReason || null }),
        });
      } else if (mode === "approve") {
        await kycApi.request(`/admin/kyc/${detail.id}/approve`, {
          method: "POST",
          body: JSON.stringify({ reviewer_notes: reviewerNotes || null }),
        });
      } else if (mode === "reject") {
        await kycApi.request(`/admin/kyc/${detail.id}/reject`, {
          method: "POST",
          body: JSON.stringify({
            reason_template: reasonTemplate,
            free_text: freeText || null,
          }),
        });
      } else if (mode === "resubmit") {
        await kycApi.request(`/admin/kyc/${detail.id}/request-resubmit`, {
          method: "POST",
          body: JSON.stringify({
            reason_template: reasonTemplate,
            free_text: freeText || null,
            docs_requested: docsRequested,
          }),
        });
      } else if (mode === "suspend") {
        await kycApi.request(`/admin/kyc/${detail.id}/suspend`, {
          method: "POST",
          body: JSON.stringify({ reason: lifecycleReason }),
        });
      } else if (mode === "revoke") {
        await kycApi.request(`/admin/kyc/${detail.id}/revoke`, {
          method: "POST",
          body: JSON.stringify({ reason: lifecycleReason }),
        });
      }
      setMessage(td("success"));
      setMode(null);
      onDecided();
    } catch {
      setError(td("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4 rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-text">{td("decisions")}</h2>

      {detail.reviewed_at ? (
        <dl className="space-y-1 rounded-md border border-border p-3 text-sm">
          <dt className="font-medium text-text">{td("decisionEvidence")}</dt>
          <dd className="text-muted">
            {td("reviewedBy")}: {detail.reviewed_by ?? "—"}
          </dd>
          <dd className="text-muted">
            {td("reviewedAt")}: {detail.reviewed_at}
          </dd>
          <dd className="text-muted">
            {td("decisionReason")}: {detail.decision_reason ?? "—"}
          </dd>
        </dl>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {detail.status === "submitted" ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium"
            onClick={() => setMode("start_review")}
          >
            {td("startReview")}
          </button>
        ) : null}
        {reviewable ? (
          <>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-white"
              onClick={() => setMode("approve")}
            >
              {td("approve")}
            </button>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger"
              onClick={() => setMode("reject")}
            >
              {td("reject")}
            </button>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-warning px-4 text-sm font-medium text-warning"
              onClick={() => setMode("resubmit")}
            >
              {td("requestResubmit")}
            </button>
          </>
        ) : null}
        {approved ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-warning px-4 text-sm font-medium text-warning"
            onClick={() => setMode("suspend")}
          >
            {td("suspend")}
          </button>
        ) : null}
        {approved || suspended ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger"
            onClick={() => setMode("revoke")}
          >
            {td("revoke")}
          </button>
        ) : null}
      </div>

      {mode === "approve" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">{td("confirmApprove", { tier: detail.tier })}</p>
          <label className="block space-y-1 text-sm">
            <span>{td("reviewerNotes")}</span>
            <textarea
              className="min-h-20 w-full rounded-md border border-border p-2"
              value={reviewerNotes}
              onChange={(event) => setReviewerNotes(event.target.value)}
            />
          </label>
        </div>
      ) : null}

      {mode === "start_review" || mode === "suspend" || mode === "revoke" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            {mode === "start_review"
              ? td("confirmStartReview")
              : mode === "suspend"
                ? td("confirmSuspend")
                : td("confirmRevoke")}
          </p>
          {mode !== "start_review" ? (
            <label className="block space-y-1 text-sm">
              <span>{td("lifecycleReason")}</span>
              <textarea
                className="min-h-20 w-full rounded-md border border-border p-2"
                value={lifecycleReason}
                onChange={(event) => setLifecycleReason(event.target.value)}
              />
            </label>
          ) : null}
        </div>
      ) : null}

      {mode === "reject" || mode === "resubmit" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            {mode === "reject" ? td("confirmReject") : td("confirmResubmit")}
          </p>
          <label className="block space-y-1 text-sm">
            <span>{td("reasonTemplate")}</span>
            <select
              className="min-h-11 w-full rounded-md border border-border px-2"
              value={reasonTemplate}
              onChange={(event) => setReasonTemplate(event.target.value as RejectReasonTemplate)}
            >
              {REASON_TEMPLATES.map((template) => (
                <option key={template} value={template}>
                  {tr(template)}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm">
            <span>{td("freeText")}</span>
            <textarea
              className="min-h-20 w-full rounded-md border border-border p-2"
              value={freeText}
              onChange={(event) => setFreeText(event.target.value)}
            />
          </label>
          {mode === "resubmit" ? (
            <fieldset className="space-y-2 text-sm">
              <legend>{td("docsRequested")}</legend>
              <label className="flex min-h-11 items-center gap-2">
                <input
                  checked={docsRequested.includes("nrc")}
                  type="checkbox"
                  onChange={() => toggleDoc("nrc")}
                />
                {td("nrc")}
              </label>
              <label className="flex min-h-11 items-center gap-2">
                <input
                  checked={docsRequested.includes("selfie")}
                  type="checkbox"
                  onChange={() => toggleDoc("selfie")}
                />
                {td("selfie")}
              </label>
            </fieldset>
          ) : null}
        </div>
      ) : null}

      {mode ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={
              submitting ||
              ((mode === "suspend" || mode === "revoke") && lifecycleReason.trim().length < 3)
            }
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
            onClick={() => void submit()}
          >
            {submitting ? td("submitting") : td("confirmAction")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            onClick={() => setMode(null)}
          >
            {td("cancel")}
          </button>
        </div>
      ) : null}

      {message ? <p className="text-sm text-success">{message}</p> : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </section>
  );
}
