"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type KycDetail, type RejectReasonTemplate, kycApi } from "./api";

type DecisionPanelProps = {
  detail: KycDetail;
  onDecided: () => void;
};

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
  const [mode, setMode] = useState<"approve" | "reject" | "resubmit" | null>(null);
  const [reasonTemplate, setReasonTemplate] = useState<RejectReasonTemplate>("blurry_document");
  const [freeText, setFreeText] = useState("");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [docsRequested, setDocsRequested] = useState<Array<"nrc" | "selfie">>(["nrc", "selfie"]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      if (mode === "approve") {
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
    <section className="space-y-4 rounded-md border border-[#E8DFD0] p-4">
      <h2 className="text-sm font-semibold text-[#2A2118]">{td("decisions")}</h2>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md bg-[#2D6A4F] px-4 text-sm font-medium text-white"
          onClick={() => setMode("approve")}
        >
          {td("approve")}
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#9B2C2C] px-4 text-sm font-medium text-[#9B2C2C]"
          onClick={() => setMode("reject")}
        >
          {td("reject")}
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#B7791F] px-4 text-sm font-medium text-[#B7791F]"
          onClick={() => setMode("resubmit")}
        >
          {td("requestResubmit")}
        </button>
      </div>

      {mode === "approve" ? (
        <div className="space-y-3">
          <p className="text-sm text-[#6B5E4C]">{td("confirmApprove", { tier: detail.tier })}</p>
          <label className="block space-y-1 text-sm">
            <span>{td("reviewerNotes")}</span>
            <textarea
              className="min-h-20 w-full rounded-md border border-[#E8DFD0] p-2"
              value={reviewerNotes}
              onChange={(event) => setReviewerNotes(event.target.value)}
            />
          </label>
        </div>
      ) : null}

      {mode === "reject" || mode === "resubmit" ? (
        <div className="space-y-3">
          <p className="text-sm text-[#6B5E4C]">
            {mode === "reject" ? td("confirmReject") : td("confirmResubmit")}
          </p>
          <label className="block space-y-1 text-sm">
            <span>{td("reasonTemplate")}</span>
            <select
              className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-2"
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
              className="min-h-20 w-full rounded-md border border-[#E8DFD0] p-2"
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
            disabled={submitting}
            className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-4 text-sm font-medium text-white disabled:opacity-60"
            onClick={() => void submit()}
          >
            {submitting ? td("submitting") : td("confirmAction")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
            onClick={() => setMode(null)}
          >
            {td("cancel")}
          </button>
        </div>
      ) : null}

      {message ? <p className="text-sm text-[#2D6A4F]">{message}</p> : null}
      {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}
    </section>
  );
}
