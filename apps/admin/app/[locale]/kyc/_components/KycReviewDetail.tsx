"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kycApi.request<KycDetail>(`/admin/kyc/${kycId}`);
      setDetail(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [kycId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{t("loading")}</p>;
  }

  if (error || !detail) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error ?? t("error")}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  const momo = detail.momo_name_match;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className="text-sm font-medium text-[#2D4A7A] underline-offset-2 hover:underline"
          href={`/${locale}/kyc`}
        >
          {t("back")}
        </Link>
        <SlaBadge badge={detail.sla_badge} />
      </div>

      <header className="space-y-1">
        <h1 className="font-serif text-xl text-[#2A2118]">{detail.vendor_display_name}</h1>
        <p className="text-sm text-[#6B5E4C]">
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
        <h2 className="text-sm font-semibold text-[#2A2118]">{t("momoMatch")}</h2>
        {momo ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-[#6B5E4C]">{t("momoPhone")}</dt>
              <dd>{momo.phone}</dd>
            </div>
            <div>
              <dt className="text-[#6B5E4C]">{t("momoOperator")}</dt>
              <dd>{momo.operator}</dd>
            </div>
            <div>
              <dt className="text-[#6B5E4C]">{t("legalName")}</dt>
              <dd>{momo.legal_name}</dd>
            </div>
            <div>
              <dt className="text-[#6B5E4C]">{t("resolvedName")}</dt>
              <dd>{momo.resolved_name ?? t("missingValue")}</dd>
            </div>
            <div>
              <dt className="text-[#6B5E4C]">{t("matchScore")}</dt>
              <dd>{momo.match_score.toFixed(2)}</dd>
            </div>
            <div>
              <dt className="text-[#6B5E4C]">{t("matchResult")}</dt>
              <dd className={momo.matched ? "text-[#2D6A4F]" : "text-[#9B2C2C]"}>
                {momo.matched ? t("matched") : t("notMatched")}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-[#6B5E4C]">{t("missingValue")}</p>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-[#2A2118]">{t("documents")}</h2>
        <DocViewer documents={detail.documents} docsAvailable={detail.docs_available} />
      </section>

      <DecisionPanel detail={detail} onDecided={() => void load()} />
    </div>
  );
}
