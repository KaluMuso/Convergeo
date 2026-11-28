"use client";

import { Modal } from "@vergeo/ui/src/modal";
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
    <Modal
      open
      title={t("confirmTitle")}
      onClose={submitting ? () => undefined : onCancel}
      closeOnEscape={!submitting}
      closeOnScrimClick={!submitting}
      panelStyle={{ width: "min(100% - 2rem, 32rem)" }}
      data-testid="merge-confirm-dialog"
    >
      <p className="text-sm text-muted">{t("confirmBody")}</p>
      <div className="mt-4 space-y-2 text-sm">
        <p>
          <span className="text-muted">{t("confirmSurvivor")}</span>
          <span className="font-medium text-text"> {survivor.name}</span>
        </p>
        <p>
          <span className="text-muted">{t("confirmLoser")}</span>
          <span className="font-medium text-text"> {loser.name}</span>
        </p>
      </div>
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-4 text-sm"
          onClick={onCancel}
          disabled={submitting}
        >
          {t("cancel")}
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)]"
          onClick={() => void handleConfirm()}
          disabled={submitting}
        >
          {submitting ? t("submitting") : t("confirmAction")}
        </button>
      </div>
    </Modal>
  );
}
