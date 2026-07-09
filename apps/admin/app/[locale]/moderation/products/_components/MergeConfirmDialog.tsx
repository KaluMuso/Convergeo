"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type DuplicatePair, moderationApi } from "./api";

type MergeConfirmDialogProps = {
  pair: DuplicatePair;
  survivorId: string;
  onCancel: () => void;
  onMerged: (idempotent: boolean) => void;
};

export function MergeConfirmDialog({
  pair,
  survivorId,
  onCancel,
  onMerged,
}: MergeConfirmDialogProps) {
  const t = useTranslations("admin.moderation.queue");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const survivor = pair.product_a.id === survivorId ? pair.product_a : pair.product_b;
  const loser = pair.product_a.id === survivorId ? pair.product_b : pair.product_a;

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await moderationApi.request<{
        idempotent: boolean;
      }>("/admin/products/merge", {
        method: "POST",
        body: JSON.stringify({
          survivor_id: survivor.id,
          loser_id: loser.id,
        }),
      });
      onMerged(result.idempotent);
    } catch {
      setError(t("failure"));
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#241B30]/50 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-dialog-title"
    >
      <div className="w-full max-w-lg space-y-4 rounded-lg border border-[#E8DFD0] bg-white p-4 shadow-lg">
        <header className="space-y-1">
          <h2 id="merge-dialog-title" className="font-serif text-lg text-[#2A2118]">
            {t("confirmTitle")}
          </h2>
          <p className="text-sm text-[#6B5E4C]">{t("confirmBody")}</p>
        </header>
        <div className="space-y-2 text-sm">
          <p>
            <span className="text-[#6B5E4C]">{t("confirmSurvivor")}</span>
            <span className="font-medium text-[#2A2118]"> {survivor.name}</span>
          </p>
          <p>
            <span className="text-[#6B5E4C]">{t("confirmLoser")}</span>
            <span className="font-medium text-[#2A2118]"> {loser.name}</span>
          </p>
        </div>
        {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-[#E8DFD0] px-4 text-sm"
            onClick={onCancel}
            disabled={submitting}
          >
            {t("cancel")}
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 items-center justify-center rounded-md bg-[#2D4A7A] px-4 text-sm font-medium text-white"
            onClick={() => void handleConfirm()}
            disabled={submitting}
          >
            {submitting ? t("submitting") : t("confirmAction")}
          </button>
        </div>
      </div>
    </div>
  );
}
