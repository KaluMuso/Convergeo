"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type DisputeDetail, disputesApi } from "./api";
import { ContextPanel } from "./ContextPanel";
import { DecisionPanel } from "./DecisionPanel";
import { DisputeSlaBadge } from "./DisputeSlaBadge";
import { EvidenceViewer } from "./EvidenceViewer";

type DisputeReviewDetailProps = {
  locale: string;
  disputeId: string;
};

export function DisputeReviewDetail({ locale, disputeId }: DisputeReviewDetailProps) {
  const t = useTranslations("admin.disputes.detail");
  const [detail, setDetail] = useState<DisputeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await disputesApi.request<DisputeDetail>(`/admin/disputes/${disputeId}`);
      setDetail(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [disputeId, t]);

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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className="text-sm font-medium text-[#2D4A7A] underline-offset-2 hover:underline"
          href={`/${locale}/disputes`}
        >
          {t("back")}
        </Link>
        <DisputeSlaBadge badge={detail.sla_badge} />
      </div>

      <header className="space-y-1">
        <h1 className="font-serif text-xl text-[#2A2118]">{t("title")}</h1>
        <p className="text-sm text-[#6B5E4C]">
          {t("summary", {
            orderId: detail.order_id,
            status: detail.status,
            vendor: detail.order.vendor_display_name,
          })}
        </p>
      </header>

      {detail.vendor_response ? (
        <section className="space-y-2 rounded-md border border-[#E8DFD0] p-4">
          <h2 className="text-sm font-semibold text-[#2A2118]">{t("vendorResponse")}</h2>
          <p className="text-sm text-[#2A2118]">{detail.vendor_response}</p>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-[#2A2118]">{t("evidenceTitle")}</h2>
        <EvidenceViewer evidence={detail.evidence} evidenceAvailable={detail.evidence_available} />
      </section>

      <section className="space-y-3 rounded-md border border-[#E8DFD0] p-4">
        <h2 className="text-sm font-semibold text-[#2A2118]">{t("contextTitle")}</h2>
        <ContextPanel locale={locale} order={detail.order} />
      </section>

      <DecisionPanel detail={detail} onDecided={() => void load()} />
    </div>
  );
}
