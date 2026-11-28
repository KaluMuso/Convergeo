"use client";

import { Modal } from "@vergeo/ui/src/modal";
import { useTranslations } from "next-intl";
import { useState } from "react";

type ConfirmDiffDialogProps = {
  open: boolean;
  dangerous?: boolean;
  fromLabel: string;
  toLabel: string;
  fromValue: string;
  toValue: string;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
};

export function ConfirmDiffDialog({
  open,
  dangerous = false,
  fromLabel,
  toLabel,
  fromValue,
  toValue,
  onCancel,
  onConfirm,
}: ConfirmDiffDialogProps) {
  const t = useTranslations("admin.config");
  const [pending, setPending] = useState(false);

  return (
    <Modal
      open={open}
      title={t("confirm.title")}
      onClose={pending ? () => undefined : onCancel}
      closeOnEscape={!pending}
      closeOnScrimClick={!pending}
      panelStyle={{ width: "min(100% - 2rem, 28rem)" }}
      data-testid="confirm-diff-dialog"
    >
      <p className="text-sm text-muted">{t("confirm.body")}</p>
      {dangerous ? (
        <p className="mt-2 text-sm font-medium text-danger">{t("confirm.dangerous")}</p>
      ) : null}

      <dl className="mt-4 grid grid-cols-2 gap-3 rounded-md bg-bg p-3 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">
            {fromLabel || t("confirm.from")}
          </dt>
          <dd className="mt-1 font-mono text-text">{fromValue}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">
            {toLabel || t("confirm.to")}
          </dt>
          <dd className="mt-1 font-mono font-semibold text-primary">{toValue}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
          onClick={onCancel}
          disabled={pending}
        >
          {t("common.cancel")}
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)] disabled:opacity-60"
          disabled={pending}
          onClick={async () => {
            setPending(true);
            try {
              await onConfirm();
            } finally {
              setPending(false);
            }
          }}
        >
          {t("common.confirm")}
        </button>
      </div>
    </Modal>
  );
}
