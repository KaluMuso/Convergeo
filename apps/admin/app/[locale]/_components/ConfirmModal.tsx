"use client";

import { Modal } from "@vergeo/ui/src/modal";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

type ConfirmModalProps = {
  open: boolean;
  title: string;
  /** Plain-language statement of exactly what will happen. */
  summary: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  /** Extra form fields (e.g. required reason). */
  children?: ReactNode;
  /** Disable confirm until the caller's required inputs are valid. */
  canConfirm?: boolean;
  /** Resolve true on success to close; throw / resolve false to keep open. */
  onConfirm: () => Promise<boolean | void>;
  onClose: () => void;
  /** Error from the last attempt. */
  error?: string | null;
  "data-testid"?: string;
};

/**
 * Admin confirmation dialog on the shared Modal (focus trap, ESC, scroll lock).
 * Every irreversible or money/status-moving action goes through this.
 */
export function ConfirmModal({
  open,
  title,
  summary,
  confirmLabel,
  destructive = false,
  children,
  canConfirm = true,
  onConfirm,
  onClose,
  error,
  "data-testid": testId,
}: ConfirmModalProps) {
  const t = useTranslations("admin.common");
  const [pending, setPending] = useState(false);

  const run = async () => {
    setPending(true);
    try {
      const result = await onConfirm();
      if (result !== false) onClose();
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeOnEscape={!pending}
      closeOnScrimClick={!pending}
      data-testid={testId}
    >
      <div className="space-y-4">
        <div className="text-sm text-text-2">{summary}</div>
        {children}
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap justify-end gap-3">
          <button
            type="button"
            disabled={pending}
            onClick={onClose}
            className="inline-flex min-h-11 items-center rounded-md border border-border px-5 text-sm font-medium text-text disabled:opacity-60"
          >
            {t("cancel")}
          </button>
          <button
            type="button"
            disabled={pending || !canConfirm}
            onClick={() => void run()}
            data-testid={testId ? `${testId}-confirm` : undefined}
            className={`inline-flex min-h-11 items-center rounded-md px-5 text-sm font-semibold disabled:opacity-50 ${
              destructive ? "bg-danger text-on-danger" : "bg-primary text-[var(--primary-btn-fg)]"
            }`}
          >
            {pending ? t("working") : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
