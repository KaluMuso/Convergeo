"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { LoadingBlock } from "../../_components/StateBlocks";

import {
  branchesApi,
  decisionErrorKey,
  mapsUrl,
  safeEvidenceUrl,
  type BranchDetail,
  type Decision,
} from "./api";
import { FlagList } from "./FlagList";

type Props = { locale: string; branchId: string };

export function BranchReview({ locale, branchId }: Props) {
  const t = useTranslations("admin");
  const [detail, setDetail] = useState<BranchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await branchesApi.request<BranchDetail>(`/admin/branches/${branchId}`));
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(`branches.queue.${failure.messageKey}`));
    } finally {
      setLoading(false);
    }
  }, [branchId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (decision: Decision) => {
    const trimmed = note.trim();
    if (decision !== "approve" && trimmed.length < 3) {
      setActionError("branches.errors.noteRequired");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await branchesApi.request(`/admin/branches/${branchId}/${decision}`, {
        method: "POST",
        body: JSON.stringify(trimmed ? { note: trimmed } : {}),
      });
      setNote("");
      await load();
    } catch (err) {
      setActionError(decisionErrorKey(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingBlock label={t("branches.queue.loading")} />;
  if (error || !detail) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error ?? t("branches.queue.error")}
        retryLabel={t("branches.queue.retry")}
        onRetry={() => void load()}
      />
    );
  }

  const openFlags = detail.flags.filter((flag) => flag.status === "open");
  const reviewable = detail.branch_status === "pending_review";
  const row = (label: string, value: React.ReactNode) => (
    <div className="grid grid-cols-[9rem_1fr] gap-2 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="m-0 text-text">{value}</dd>
    </div>
  );

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <Link href={`/${locale}/branches`} className="text-sm text-primary no-underline">
          {t("branches.detail.back")}
        </Link>
        <h1 className="m-0 font-serif text-xl text-text">{detail.display_name}</h1>
        <p className="m-0 text-sm text-muted">
          {t(`branches.status.${detail.branch_status}`)} ·{" "}
          {t(`branches.kind.${detail.branch_kind}`)}
        </p>
      </header>

      <section className="space-y-2 rounded-md border border-border bg-surface p-3">
        <h2 className="m-0 text-sm font-semibold text-text">{t("branches.detail.business")}</h2>
        <dl className="m-0 space-y-1">
          {row(t("branches.detail.legalName"), detail.business?.legal_name ?? "—")}
          {row(
            t("branches.detail.registration"),
            detail.business
              ? `${detail.business.registration_type}${detail.business.pacra_number ? ` · ${detail.business.pacra_number}` : ""}`
              : "—",
          )}
          {row(
            t("branches.detail.pacraCertificate"),
            safeEvidenceUrl(detail.business?.pacra_cert_url) ? (
              <a
                href={safeEvidenceUrl(detail.business?.pacra_cert_url) ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("branches.detail.open")}
              </a>
            ) : (
              "—"
            ),
          )}
          {row(
            t("branches.detail.ownerKyc"),
            detail.owner_kyc_approved ? t("branches.detail.yes") : t("branches.detail.no"),
          )}
        </dl>
      </section>

      <section className="space-y-2 rounded-md border border-border bg-surface p-3">
        <h2 className="m-0 text-sm font-semibold text-text">{t("branches.detail.shop")}</h2>
        <dl className="m-0 space-y-1">
          {row(
            t("branches.detail.location"),
            detail.location ? (
              <a
                href={mapsUrl(detail.location.lat, detail.location.lng)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {detail.location.landmark}
              </a>
            ) : (
              "—"
            ),
          )}
          {row(t("branches.detail.address"), detail.location?.address ?? "—")}
          {row(t("branches.detail.phone"), detail.contact_phone ?? "—")}
          {row(
            t("branches.detail.payout"),
            `${detail.payout_msisdn_masked ?? "—"} ${detail.payout_rail ?? ""}${detail.payout_on_hold ? ` · ${t("branches.detail.onHold")}` : ""}`,
          )}
          {row(
            t("branches.detail.plan"),
            detail.plan
              ? detail.plan.branch_billing_role === "addon" &&
                detail.plan.addon_price_ngwee !== null
                ? t("branches.detail.planAddon", {
                    plan: detail.plan.plan_key,
                    price: formatK(detail.plan.addon_price_ngwee),
                  })
                : t("branches.detail.planIncluded", { plan: detail.plan.plan_key })
              : "—",
          )}
        </dl>
      </section>

      <section className="space-y-2 rounded-md border border-border bg-surface p-3">
        <h2 className="m-0 text-sm font-semibold text-text">{t("branches.detail.evidence")}</h2>
        {detail.evidence.length === 0 ? (
          <p className="m-0 text-sm text-muted">{t("branches.detail.noEvidence")}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {detail.evidence.map((item) => {
              const url = safeEvidenceUrl(item.signed_url);
              return (
                <figure key={item.kind} className="m-0 space-y-1">
                  {url ? (
                    <img
                      src={url}
                      alt={t(`branches.evidence.${item.kind}`)}
                      className="max-h-64 w-full rounded-md object-contain"
                      loading="lazy"
                    />
                  ) : (
                    <p className="m-0 text-sm text-muted">{t("branches.detail.unavailable")}</p>
                  )}
                  <figcaption className="text-xs text-muted">
                    {t(`branches.evidence.${item.kind}`)}
                    {item.proof_type ? ` · ${t(`branches.proof.${item.proof_type}`)}` : ""}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="m-0 text-sm font-semibold text-text">
          {t("branches.detail.flags", { count: openFlags.length })}
        </h2>
        <FlagList flags={detail.flags} onResolved={() => void load()} />
      </section>

      {detail.siblings.length > 0 ? (
        <section className="space-y-1 text-sm">
          <h2 className="m-0 text-sm font-semibold text-text">{t("branches.detail.siblings")}</h2>
          <ul className="m-0 list-disc pl-5 text-text-2">
            {detail.siblings.map((sibling) => (
              <li key={sibling.id}>
                {sibling.display_name} · {t(`branches.status.${sibling.branch_status}`)}
                {sibling.is_primary ? ` · ${t("branches.detail.primary")}` : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {reviewable ? (
        <section className="space-y-2 rounded-md border border-border bg-surface p-3">
          <label className="flex flex-col gap-1 text-sm text-text-2">
            {t("branches.detail.note")}
            <textarea
              className="min-h-20 rounded-md border border-border bg-surface p-2 text-sm text-text"
              maxLength={1000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {openFlags.length > 0 ? (
            <p className="m-0 text-sm text-accent-deep">{t("branches.detail.flagsBlock")}</p>
          ) : null}
          {actionError ? (
            <p role="alert" className="m-0 text-sm text-danger">
              {t(actionError)}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || openFlags.length > 0}
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-surface disabled:opacity-60"
              onClick={() => void decide("approve")}
            >
              {t("branches.actions.approve")}
            </button>
            <button
              type="button"
              disabled={busy}
              className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
              onClick={() => void decide("request-info")}
            >
              {t("branches.actions.requestInfo")}
            </button>
            <button
              type="button"
              disabled={busy}
              className="inline-flex min-h-11 items-center rounded-md bg-danger px-3 text-sm font-medium text-on-danger"
              onClick={() => void decide("reject")}
            >
              {t("branches.actions.reject")}
            </button>
          </div>
        </section>
      ) : null}

      <section className="space-y-1 text-sm">
        <h2 className="m-0 text-sm font-semibold text-text">{t("branches.detail.history")}</h2>
        <ol className="m-0 list-decimal pl-5 text-text-2">
          {detail.history.map((event, index) => (
            <li key={`${event.to_status}-${index}`}>
              {t(`branches.status.${event.to_status}`)}
              {event.note ? ` · ${event.note}` : ""}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
