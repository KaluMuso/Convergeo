"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmModal } from "../../_components/ConfirmModal";

import { type KycDetail, type RejectReasonTemplate, kycApi } from "./api";

type DecisionPanelProps = {
  detail: KycDetail;
  /** Review checklist complete; approving is blocked until it is. */
  checklistComplete?: boolean;
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

const LICENSE_BODIES = [
  "PACRA",
  "ZAMRA",
  "HPCZ",
  "ZIEA",
  "RTSA",
  "ZEMA",
  "ERB",
  "WARMA",
  "TCZ",
  "OTHER",
] as const;

const REGULATED_CLASSES = [
  "pharmacy",
  "agrochemicals",
  "alcohol",
  "food",
  "financial_services",
] as const;

export function DecisionPanel({ detail, checklistComplete = true, onDecided }: DecisionPanelProps) {
  const td = useTranslations("admin.kyc.detail");
  const tr = useTranslations("admin.kyc.reasons");
  const [mode, setMode] = useState<DecisionMode | null>(null);
  const [reasonTemplate, setReasonTemplate] = useState<RejectReasonTemplate | "">("");
  const [freeText, setFreeText] = useState("");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [licenseBody, setLicenseBody] = useState<
    "PACRA" | "ZAMRA" | "HPCZ" | "ZIEA" | "RTSA" | "ZEMA" | "ERB" | "WARMA" | "TCZ" | "OTHER"
  >("HPCZ");
  const [regulatedClass, setRegulatedClass] = useState<
    "pharmacy" | "agrochemicals" | "alcohol" | "food" | "financial_services"
  >("pharmacy");
  const [licenceNumber, setLicenceNumber] = useState("");
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

  const submit = async (): Promise<boolean> => {
    if ((mode === "reject" || mode === "resubmit") && !reasonTemplate) return false;
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
        const payload: Record<string, string | null> = {
          reviewer_notes: reviewerNotes || null,
        };
        if (detail.tier >= 2) {
          payload.expiry_date = expiryDate;
          payload.license_body = licenseBody;
          payload.regulated_class = regulatedClass;
          payload.licence_number = licenceNumber.trim();
        }
        await kycApi.request(`/admin/kyc/${detail.id}/approve`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else if (mode === "reject") {
        await kycApi.request(`/admin/kyc/${detail.id}/reject`, {
          method: "POST",
          body: JSON.stringify({
            reason_template: reasonTemplate as RejectReasonTemplate,
            free_text: freeText || null,
          }),
        });
      } else if (mode === "resubmit") {
        await kycApi.request(`/admin/kyc/${detail.id}/request-resubmit`, {
          method: "POST",
          body: JSON.stringify({
            reason_template: reasonTemplate as RejectReasonTemplate,
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
      return true;
    } catch {
      setError(td("failure"));
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const closeMode = () => {
    setMode(null);
    setError(null);
  };
  const reasonMissing =
    (mode === "reject" || mode === "resubmit") &&
    (!reasonTemplate || (reasonTemplate === "other" && !freeText.trim()));
  const lifecycleMissing =
    (mode === "suspend" || mode === "revoke") && lifecycleReason.trim().length < 3;
  const approveMissing =
    mode === "approve" && detail.tier >= 2 && (!expiryDate || licenceNumber.trim().length < 3);
  const modeTitle = mode
    ? {
        approve: td("approve"),
        reject: td("reject"),
        resubmit: td("requestResubmit"),
        start_review: td("startReview"),
        suspend: td("suspend"),
        revoke: td("revoke"),
      }[mode]
    : "";
  const vendorSees = [reasonTemplate ? tr(reasonTemplate) : null, freeText.trim() || null]
    .filter(Boolean)
    .join(" — ");

  return (
    <section className="space-y-4 rounded-lg border border-border bg-surface p-4">
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
              disabled={!checklistComplete}
              className="inline-flex min-h-11 items-center rounded-md bg-success px-4 text-sm font-medium text-on-danger disabled:opacity-50"
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

      {!checklistComplete && reviewable ? (
        <p className="text-xs text-muted" data-testid="checklist-hint">
          {td("checklistHint")}
        </p>
      ) : null}

      {message ? (
        <p role="status" className="text-sm text-success">
          {message}
        </p>
      ) : null}

      <ConfirmModal
        open={mode !== null}
        title={modeTitle}
        destructive={mode === "reject" || mode === "revoke" || mode === "suspend"}
        confirmLabel={modeTitle}
        canConfirm={!submitting && !reasonMissing && !lifecycleMissing && !approveMissing}
        onConfirm={submit}
        onClose={closeMode}
        error={error}
        data-testid="kyc-confirm"
        summary={
          <div className="space-y-2">
            <p>{td("vendorWillBeNotified", { vendor: detail.vendor_display_name })}</p>
            {mode === "reject" || mode === "resubmit" ? (
              <p className="rounded-md bg-bg p-2 text-xs" data-testid="vendor-sees">
                <span className="font-medium text-text">{td("vendorSees")}</span>{" "}
                {vendorSees || td("vendorSeesEmpty")}
              </p>
            ) : null}
          </div>
        }
      >
        <div className="space-y-3">
          {mode === "approve" ? (
            <div className="space-y-3">
              <p className="text-sm text-muted">{td("confirmApprove", { tier: detail.tier })}</p>
              {detail.tier >= 2 ? (
                <>
                  <p className="text-sm text-warning">{td("licenseRequired")}</p>
                  <label className="block space-y-1 text-sm">
                    <span>{td("expiryDate")}</span>
                    <input
                      className="min-h-11 w-full rounded-md border border-border px-2"
                      type="date"
                      value={expiryDate}
                      onChange={(event) => setExpiryDate(event.target.value)}
                      required
                    />
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span>{td("licenseBody")}</span>
                    <select
                      className="min-h-11 w-full rounded-md border border-border px-2"
                      value={licenseBody}
                      onChange={(event) => setLicenseBody(event.target.value as typeof licenseBody)}
                    >
                      {LICENSE_BODIES.map((body) => (
                        <option key={body} value={body}>
                          {td(`licenseBodies.${body}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span>{td("regulatedClass")}</span>
                    <select
                      className="min-h-11 w-full rounded-md border border-border px-2"
                      value={regulatedClass}
                      onChange={(event) =>
                        setRegulatedClass(event.target.value as typeof regulatedClass)
                      }
                    >
                      {REGULATED_CLASSES.map((regulatedClassKey) => (
                        <option key={regulatedClassKey} value={regulatedClassKey}>
                          {td(`regulatedClasses.${regulatedClassKey}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span>{td("licenceNumber")}</span>
                    <input
                      className="min-h-11 w-full rounded-md border border-border px-2"
                      value={licenceNumber}
                      onChange={(event) => setLicenceNumber(event.target.value)}
                      required
                    />
                  </label>
                </>
              ) : null}
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
                  required
                  onChange={(event) =>
                    setReasonTemplate(event.target.value as RejectReasonTemplate)
                  }
                >
                  <option value="">{td("reasonPlaceholder")}</option>
                  {REASON_TEMPLATES.map((template) => (
                    <option key={template} value={template}>
                      {tr(template)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1 text-sm">
                <span>{reasonTemplate === "other" ? td("freeTextRequired") : td("freeText")}</span>
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
        </div>
      </ConfirmModal>
    </section>
  );
}
