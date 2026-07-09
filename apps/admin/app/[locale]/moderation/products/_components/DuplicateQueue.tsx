"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type DuplicatePair, moderationApi } from "./api";
import { MergeConfirmDialog } from "./MergeConfirmDialog";
import { ProductCompareCard } from "./ProductCompareCard";

export function DuplicateQueue() {
  const t = useTranslations("admin.moderation.queue");
  const [pairs, setPairs] = useState<DuplicatePair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPair, setSelectedPair] = useState<DuplicatePair | null>(null);
  const [survivorId, setSurvivorId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const data = await moderationApi.request<DuplicatePair[]>("/admin/products/duplicates");
      setPairs(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const openMerge = (pair: DuplicatePair, survivor: string) => {
    setSelectedPair(pair);
    setSurvivorId(survivor);
  };

  const closeMerge = () => {
    setSelectedPair(null);
    setSurvivorId(null);
  };

  const handleMerged = async (idempotent: boolean) => {
    closeMerge();
    setMessage(idempotent ? t("idempotent") : t("success"));
    await load();
  };

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error}</p>
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

  if (pairs.length === 0) {
    return <p className="text-sm text-[#6B5E4C]">{t("empty")}</p>;
  }

  return (
    <div className="space-y-4">
      {message ? <p className="text-sm text-[#2D4A7A]">{message}</p> : null}
      <div className="space-y-4">
        {pairs.map((pair) => {
          const pairKey = `${pair.product_a.id}:${pair.product_b.id}`;
          return (
            <article key={pairKey} className="space-y-3 rounded-lg border border-[#E8DFD0] p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-[#6B5E4C]">
                  {t("similarityPercent", { value: (pair.similarity * 100).toFixed(1) })}
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <ProductCompareCard
                  product={pair.product_a}
                  actionLabel={t("merge")}
                  onSelectSurvivor={() => openMerge(pair, pair.product_a.id)}
                />
                <ProductCompareCard
                  product={pair.product_b}
                  actionLabel={t("merge")}
                  onSelectSurvivor={() => openMerge(pair, pair.product_b.id)}
                />
              </div>
            </article>
          );
        })}
      </div>
      {selectedPair && survivorId ? (
        <MergeConfirmDialog
          pair={selectedPair}
          survivorId={survivorId}
          onCancel={closeMerge}
          onMerged={handleMerged}
        />
      ) : null}
    </div>
  );
}
