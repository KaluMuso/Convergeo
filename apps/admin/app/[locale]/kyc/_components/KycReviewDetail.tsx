"use client";

import { ApiError } from "@vergeo/config";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { adminPrimaryButtonClass } from "../../_components/admin-primary-button";
import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { LoadingBlock } from "../../_components/StateBlocks";

import { type KycDetail, prefetchKycDetail } from "./api";
import { DecisionPanel } from "./DecisionPanel";
import { DocViewer } from "./DocViewer";
import { EMPTY_CHECKS, isChecklistComplete, KycChecklist, type KycChecks } from "./KycChecklist";
import { SlaBadge } from "./SlaBadge";

type KycReviewDetailProps = {
  locale: string;
  kycId: string;
};

export function KycReviewDetail({ locale, kycId }: KycReviewDetailProps) {
  const t = useTranslations("admin.kyc.detail");
  const [detail, setDetail] = useState<KycDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [checks, setChecks] = useState<KycChecks>(EMPTY_CHECKS);
  const [requestedDecision, setRequestedDecision] = useState<"approve" | "resubmit" | null>(null);

  const load = useCallback(async () => {
    setLoadingDetail(true);
    setError(null);
    setPermissionDenied(false);
    setNotFound(false);
    try {
      const data = await prefetchKycDetail(kycId);
      setDetail(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
        setDetail(null);
        return;
      }
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, [kycId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loadingDetail && !detail && !error && !notFound) {
    return (
      <div className="space-y-6">
        <LoadingBlock label={t("loading")} rows={2} />
        <KycChecklist checks={checks} onChange={setChecks} disabled momoMatched={null} />
        <DocViewer documents={[]} docsAvailable loading />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="space-y-2" role="alert" data-testid="admin-not-found">
        <h1 className="font-serif text-xl text-text">{t("notFound")}</h1>
        <p className="text-sm text-muted">{t("notFoundBody")}</p>
        <Link
          className="text-sm font-medium text-primary underline-offset-2 hover:underline"
          href={`/${locale}/kyc`}
        >
          {t("back")}
        </Link>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error ?? t("error")}
        hint={permissionDenied ? t("permissionDeniedHint") : undefined}
        retryLabel={t("retry")}
        onRetry={() => void load()}
      />
    );
  }

  const momo = detail.momo_name_match;

  const reviewable = detail.status === "submitted" || detail.status === "under_review";

  return (
    <>
      {reviewable ? (
        <div
          className="sticky top-0 z-20 -mx-3 mb-4 flex flex-wrap items-center justify-end gap-2 border-b border-border bg-surface/95 px-3 py-3 backdrop-blur"
          data-testid="kyc-sticky-actions"
        >
          <button
            type="button"
            disabled={!isChecklistComplete(checks)}
            className={adminPrimaryButtonClass}
            onClick={() => setRequestedDecision("approve")}
          >
            {t("approve")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-warning px-4 text-sm font-medium text-warning"
            onClick={() => setRequestedDecision("resubmit")}
          >
            {t("requestResubmit")}
          </button>
        </div>
      ) : null}
      <div className="space-y-6 pb-24">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
            href={`/${locale}/kyc`}
          >
            {t("back")}
          </Link>
          <SlaBadge badge={detail.sla_badge} />
        </div>

        <header className="space-y-1">
          <h1 className="font-serif text-xl text-text">{detail.vendor_display_name}</h1>
          <p className="text-sm text-muted">
            {t("vendorSummary", {
              context: t("vendorContext"),
              slug: detail.vendor_slug,
              tierLabel: t("tierLabel", { tier: detail.tier }),
              statusLabel: t("statusLabel"),
              status: detail.status,
            })}
          </p>
        </header>

        <section className="space-y-3" aria-labelledby="kyc-docs-heading">
          <h2 id="kyc-docs-heading" className="text-sm font-semibold text-text">
            {t("documents")}
          </h2>
          <DocViewer
            documents={detail.documents}
            docsAvailable={detail.docs_available}
            loading={loadingDetail}
            onRefresh={() => void load()}
          />
        </section>

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-text">{t("momoMatch")}</h2>
              {momo ? (
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-muted">{t("momoPhone")}</dt>
                    <dd>{momo.phone}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">{t("momoOperator")}</dt>
                    <dd>{momo.operator}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">{t("legalName")}</dt>
                    <dd>{momo.legal_name}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">{t("resolvedName")}</dt>
                    <dd>{momo.resolved_name ?? t("missingValue")}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">{t("matchScore")}</dt>
                    <dd>{momo.match_score.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">{t("matchResult")}</dt>
                    <dd className={momo.matched ? "text-success" : "text-danger"}>
                      {momo.matched ? t("matched") : t("notMatched")}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-muted">{t("missingValue")}</p>
              )}
            </section>

            <KycChecklist
              checks={checks}
              onChange={setChecks}
              disabled={detail.status !== "submitted" && detail.status !== "under_review"}
              momoMatched={momo ? momo.matched : null}
            />
          </div>
          <DecisionPanel
            detail={detail}
            checklistComplete={isChecklistComplete(checks)}
            requestedMode={requestedDecision}
            onRequestedModeHandled={() => setRequestedDecision(null)}
            onDecided={() => {
              setChecks(EMPTY_CHECKS);
              void load();
            }}
          />
        </div>
      </div>
    </>
  );
}
