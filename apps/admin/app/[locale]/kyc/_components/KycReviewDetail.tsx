"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { type KycDetail, kycApi } from "./api";
import { DecisionPanel } from "./DecisionPanel";
import { DocViewer } from "./DocViewer";
import { SlaBadge } from "./SlaBadge";

type KycReviewDetailProps = {
  locale: string;
  kycId: string;
};

export function KycReviewDetail({ locale, kycId }: KycReviewDetailProps) {
  const t = useTranslations("admin.kyc.detail");
  const [detail, setDetail] = useState<KycDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const data = await kycApi.request<KycDetail>(`/admin/kyc/${kycId}`);
      setDetail(data);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [kycId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
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

  return (
    <div className="space-y-6">
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

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-text">{t("documents")}</h2>
        <DocViewer documents={detail.documents} docsAvailable={detail.docs_available} />
      </section>

      <DecisionPanel detail={detail} onDecided={() => void load()} />
    </div>
  );
}
