"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { adminClipsApi, type ClipDetail } from "./api";
import { canApprove, canReject, canTakeDown, decisionErrorKey } from "./clip-review";

/**
 * M17-P07 — preview a non-public clip and decide.
 *
 * Two things this panel refuses to do:
 *
 * * **Offer approve on media that is not ready.** The API refuses it anyway, but
 *   a button that always 422s teaches reviewers to ignore errors. The reason is
 *   shown instead.
 * * **Reject without a reason.** A rejection a vendor cannot act on is just a
 *   disappearance, so the button stays disabled until there is one.
 *
 * The preview plays from short-lived links returned by the API. This is the only
 * place in the product where an unpublished clip is watchable, and it stops
 * being watchable when the links expire.
 */
export function ClipDecisionPanel({ clipId, locale }: { clipId: string; locale: string }) {
  const t = useTranslations("admin.clips.detail");
  const tActions = useTranslations("admin.clips.actions");
  const tRoot = useTranslations("admin.clips");
  const tEscalation = useTranslations("admin.clips.escalation");

  const [detail, setDetail] = useState<ClipDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [suspended, setSuspended] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await adminClipsApi.detail(clipId));
    } catch {
      setError(tRoot("error.title"));
    } finally {
      setLoading(false);
    }
  }, [clipId, tRoot]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = useCallback(
    async (action: "approve" | "reject" | "takedown") => {
      setBusy(true);
      setError(null);
      try {
        const result =
          action === "approve"
            ? await adminClipsApi.approve(clipId)
            : action === "reject"
              ? await adminClipsApi.reject(clipId, reason)
              : await adminClipsApi.takedown(clipId, reason);
        setOutcome(result.status);
        setSuspended(Boolean(result.vendor_suspended));
        await load();
      } catch (err) {
        setError(tActions(decisionErrorKey((err as { code?: string })?.code)));
      } finally {
        setBusy(false);
      }
    },
    [clipId, load, reason, tActions],
  );

  if (loading) {
    return (
      <p className="text-sm text-muted" data-testid="admin-clip-loading">
        {tRoot("loading")}
      </p>
    );
  }

  if (!detail) {
    return (
      <p role="alert" className="text-sm text-danger">
        {tRoot("error.title")}
      </p>
    );
  }

  const renditions = Object.entries(detail.preview_urls);

  return (
    <section className="flex flex-col gap-4" data-testid="admin-clip-detail">
      <Link href={`/${locale}/clips`} className="text-sm text-primary">
        {t("back")}
      </Link>

      <h1 className="font-serif text-xl text-text">{t("title")}</h1>

      {/* Preview of a clip that is NOT public — short-lived links only. */}
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-text">{t("preview")}</h2>
        {renditions.length > 0 ? (
          <video
            data-testid="admin-clip-preview"
            src={renditions[0]?.[1]}
            poster={detail.poster_url ?? undefined}
            controls
            preload="none"
            playsInline
            className="max-h-[60vh] w-full rounded-2 bg-bg-2"
          >
            <track kind="captions" />
          </video>
        ) : (
          <p className="text-sm text-muted">{t("mediaProblems", { problems: "—" })}</p>
        )}
        <p className="text-xs text-muted">
          {t("previewExpiry", { minutes: Math.round(detail.preview_expires_in_s / 60) })}
        </p>
      </div>

      <dl className="grid grid-cols-1 gap-2 text-sm">
        <div>
          <dt className="text-muted">{t("caption")}</dt>
          {/* Untrusted vendor text — rendered as a text node, never as HTML. */}
          <dd className="text-text" data-testid="admin-clip-caption">
            {detail.caption ?? "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("duration")}</dt>
          <dd className="text-text">{detail.duration_s ? `${detail.duration_s}s` : "—"}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("screenVerdict")}</dt>
          <dd className="text-text">
            {detail.screen_verdict === "passed" ? t("screenPassed") : detail.screen_verdict}
          </dd>
        </div>
        <div>
          <dt className="text-muted">
            {t("vendorStatus", { status: detail.vendor_status ?? "—" })}
          </dt>
          <dd className="text-text">
            {detail.vendor_kyc_tier ? t("vendorTier", { tier: detail.vendor_kyc_tier }) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("reportCount", { count: detail.report_count })}</dt>
          <dd className="text-text">
            {tRoot("queue.repeatOffender", { count: detail.repeat_offender_count })}
          </dd>
        </div>
      </dl>

      {detail.linked_listings.length > 0 ? (
        <div>
          <h2 className="text-sm font-medium text-text">{t("linkedProducts")}</h2>
          <ul className="mt-1 flex flex-col gap-1 text-sm text-text">
            {detail.linked_listings.map((listing) => (
              <li key={listing.listing_id}>
                {listing.title ?? listing.listing_id} — {formatK(listing.price_ngwee, { locale })}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!detail.media_ready ? (
        <p role="alert" data-testid="admin-clip-media-problems" className="text-sm text-warning">
          {t("mediaProblems", { problems: detail.media_problems.join(", ") })}
        </p>
      ) : null}

      <label className="flex flex-col gap-1 text-sm text-text" htmlFor="clip-reason">
        {tActions("reasonLabel")}
        <textarea
          id="clip-reason"
          value={reason}
          maxLength={1000}
          placeholder={tActions("reasonPlaceholder")}
          data-testid="admin-clip-reason"
          onChange={(event) => setReason(event.target.value)}
          className="min-h-20 rounded-2 border border-border bg-surface p-2"
        />
      </label>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || !canApprove(detail)}
          onClick={() => void act("approve")}
          data-testid="admin-clip-approve"
          className="tap min-h-11 rounded-full bg-primary px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
        >
          {busy ? tActions("approving") : tActions("approve")}
        </button>
        <button
          type="button"
          disabled={busy || !canReject(detail, reason)}
          onClick={() => void act("reject")}
          data-testid="admin-clip-reject"
          className="tap min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text disabled:opacity-50"
        >
          {busy ? tActions("rejecting") : tActions("reject")}
        </button>
        {detail.status === "published" ? (
          <button
            type="button"
            disabled={busy || !canTakeDown(detail, reason)}
            onClick={() => void act("takedown")}
            data-testid="admin-clip-takedown"
            className="tap min-h-11 rounded-full border border-danger bg-surface px-4 py-2 text-sm text-danger disabled:opacity-50"
          >
            {tActions("takedown")}
          </button>
        ) : null}
      </div>

      {error ? (
        <p role="alert" data-testid="admin-clip-error" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {outcome ? (
        <p role="status" data-testid="admin-clip-outcome" className="text-sm text-success">
          {outcome === "published"
            ? tActions("approved")
            : outcome === "rejected"
              ? tActions("rejected")
              : tActions("takenDown")}
        </p>
      ) : null}

      {suspended ? (
        <p role="status" data-testid="admin-clip-suspended" className="text-sm text-danger">
          {tEscalation("suspended")}
        </p>
      ) : null}

      <p className="text-xs text-muted">{tEscalation("policy")}</p>
    </section>
  );
}
