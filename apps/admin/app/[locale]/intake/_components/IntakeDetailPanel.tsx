"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import {
  intakeActionPath,
  intakeApi,
  type IntakeAction,
  type IntakeActionResponse,
  type IntakeDetail,
} from "./api";

type IntakeDetailPanelProps = {
  locale: string;
  sessionId: string;
};

/** Actions that must carry a reason the vendor will read. */
const REASON_ACTIONS: ReadonlySet<IntakeAction> = new Set(["reject", "request-changes"]);

function draftValue(draft: Record<string, unknown>, key: string): string {
  const value = draft[key];
  if (value === null || value === undefined) return "—";
  if (key === "price_ngwee" && typeof value === "number") return formatK(value);
  return String(value);
}

const DRAFT_FIELDS = [
  "title",
  "price_ngwee",
  "condition",
  "quantity",
  "stock_mode",
  "sale_unit",
  "description",
] as const;

export function IntakeDetailPanel({ locale, sessionId }: IntakeDetailPanelProps) {
  const t = useTranslations("admin.intake");
  const tQueue = useTranslations("admin.intake.queue");
  const [detail, setDetail] = useState<IntakeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<IntakeAction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      setDetail(
        await intakeApi.request<IntakeDetail>(`/admin/intake/${encodeURIComponent(sessionId)}`),
      );
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(tQueue(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [sessionId, tQueue]);

  useEffect(() => {
    void load();
  }, [load]);

  const runAction = async (action: IntakeAction) => {
    if (REASON_ACTIONS.has(action) && reason.trim() === "") {
      setActionError(t("errors.reasonRequired"));
      return;
    }
    if (action === "attach-canonical" && candidate === "") {
      return;
    }
    setBusy(action);
    setActionError(null);
    try {
      const body: Record<string, string> = {};
      if (REASON_ACTIONS.has(action)) body.reason = reason.trim();
      if (action === "attach-canonical") body.product_id = candidate;

      await intakeApi.request<IntakeActionResponse>(intakeActionPath(sessionId, action), {
        method: "POST",
        body: Object.keys(body).length > 0 ? JSON.stringify(body) : undefined,
      });
      setReason("");
      await load();
    } catch {
      setActionError(t("errors.actionFailed"));
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  if (error || !detail) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error ?? t("errors.loadFailed")}
        retryLabel={t("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  return (
    <div className="space-y-5" data-testid="intake-detail">
      <header className="space-y-1">
        <Link href={`/${locale}/intake`} className="text-sm underline">
          {t("detail.back")}
        </Link>
        <h1 className="font-serif text-xl text-text">{t("detail.title")}</h1>
        <p className="text-sm text-muted">
          {t("detail.vendor")}: {detail.vendor_display_name ?? detail.vendor_id}
          {detail.vendor_kyc_tier === null ? "" : ` · T${detail.vendor_kyc_tier}`}
        </p>
      </header>

      {detail.warnings.length > 0 ? (
        <ul
          className="space-y-1 rounded-md border border-warning/40 bg-warning/5 p-3"
          data-testid="intake-warnings"
        >
          {detail.warnings.map((key) => (
            <li key={key} className="text-sm text-warning">
              {t(key.replace(/^admin\.intake\./, ""))}
            </li>
          ))}
        </ul>
      ) : null}

      <section className="space-y-2">
        <h2 className="text-base font-medium">{t("detail.draft")}</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {DRAFT_FIELDS.map((field) => (
            <div key={field}>
              <dt className="text-xs uppercase text-muted">{field}</dt>
              <dd>{draftValue(detail.draft, field)}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-medium">{t("detail.provenance")}</h2>
        <ul className="space-y-1 text-sm">
          {detail.provenance.map((entry) => (
            <li key={entry.field_name}>
              {entry.field_name}: {t(`source.${entry.source}`)}
              {entry.confidence === null ? "" : ` (${Math.round(entry.confidence * 100)}%)`}
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-medium">{t("detail.photos")}</h2>
        {detail.media.length === 0 ? (
          <p className="text-sm text-muted">{t("detail.noPhotos")}</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {detail.media.map((item, index) =>
              item.signed_url ? (
                <li key={item.id}>
                  {/* Short-lived signed URL over a private bucket — deliberately not
                      next/image, which would proxy and cache a quarantined asset. */}
                  <img
                    src={item.signed_url}
                    alt={t("detail.photoAlt", { position: index + 1 })}
                    className="h-28 w-28 rounded object-cover"
                    loading="lazy"
                  />
                </li>
              ) : null,
            )}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-medium">{t("detail.diff")}</h2>
        <table className="w-full text-sm">
          <tbody>
            {detail.listing_diff.map((entry) => (
              <tr key={entry.field_name} className="border-t border-border">
                <td className="p-2 text-xs uppercase text-muted">{entry.field_name}</td>
                <td className="p-2">{entry.draft_value ?? "—"}</td>
                <td className="p-2">{entry.listing_value ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {detail.canonical_candidates.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-base font-medium">{t("detail.candidates")}</h2>
          <select
            className="min-h-11 w-full rounded-md border border-border px-3"
            aria-label={t("detail.candidates")}
            value={candidate}
            onChange={(event) => setCandidate(event.target.value)}
          >
            <option value="">—</option>
            {detail.canonical_candidates.map((item) => (
              <option key={item.product_id} value={item.product_id}>
                {item.name} · {t("detail.candidateScore", { score: Math.round(item.score * 100) })}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            disabled={busy !== null || candidate === ""}
            onClick={() => void runAction("attach-canonical")}
          >
            {busy === "attach-canonical" ? t("actions.attaching") : t("actions.attachCanonical")}
          </button>
        </section>
      ) : null}

      <section className="space-y-2">
        <label className="block text-sm" htmlFor="intake-reason">
          {t("actions.reasonLabel")}
        </label>
        <textarea
          id="intake-reason"
          className="min-h-24 w-full rounded-md border border-border p-2 text-sm"
          placeholder={t("actions.reasonPlaceholder")}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />

        {actionError ? (
          <p role="alert" className="text-sm text-danger">
            {actionError}
          </p>
        ) : null}

        {/* One session, one decision. There is no bulk control here by design. */}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            disabled={busy !== null}
            onClick={() => void runAction("request-changes")}
            data-testid="intake-request-changes"
          >
            {busy === "request-changes"
              ? t("actions.requestingChanges")
              : t("actions.requestChanges")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm text-danger"
            disabled={busy !== null}
            onClick={() => void runAction("reject")}
            data-testid="intake-reject"
          >
            {busy === "reject" ? t("actions.rejecting") : t("actions.reject")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border bg-primary px-4 text-sm text-[var(--primary-btn-fg)]"
            disabled={busy !== null}
            onClick={() => void runAction("approve")}
            data-testid="intake-approve"
          >
            {busy === "approve" ? t("actions.approving") : t("actions.approve")}
          </button>
        </div>
      </section>
    </div>
  );
}
