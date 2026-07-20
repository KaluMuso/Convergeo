"use client";

import { useCallback, useState } from "react";

import { Modal } from "./modal";

export type ConfirmDialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void | Promise<void>;
  destructive?: boolean;
  "data-testid"?: string;
};

export function ConfirmDialog({
  open,
  onClose,
  title,
  body,
  confirmLabel,
  cancelLabel,
  onConfirm,
  destructive = false,
  "data-testid": dataTestId,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);

  const handleConfirm = useCallback(async () => {
    setPending(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setPending(false);
    }
  }, [onConfirm, onClose]);

  const confirmStyle: React.CSSProperties = {
    minHeight: "2.75rem",
    minWidth: "2.75rem",
    padding: "var(--sp-2) var(--sp-5)",
    border: "none",
    borderRadius: "var(--r)",
    fontSize: "var(--fs-body)",
    fontWeight: 600,
    cursor: pending ? "wait" : "pointer",
    opacity: pending ? 0.7 : 1,
    background: destructive ? "var(--danger)" : "var(--primary)",
    color: destructive ? "var(--on-danger)" : "var(--primary-btn-fg)",
    transition: `transform var(--dur) var(--ease-spring), opacity var(--dur-fast) var(--ease-std)`,
  };

  const cancelStyle: React.CSSProperties = {
    minHeight: "2.75rem",
    minWidth: "2.75rem",
    padding: "var(--sp-2) var(--sp-5)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r)",
    fontSize: "var(--fs-body)",
    fontWeight: 600,
    cursor: "pointer",
    background: "transparent",
    color: "var(--text)",
    transition: `opacity var(--dur-fast) var(--ease-std)`,
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeOnEscape={!pending}
      closeOnScrimClick={!pending}
      data-testid={dataTestId}
    >
      <p style={{ margin: "0 0 var(--sp-6)", fontSize: "var(--fs-body)", color: "var(--text-2)" }}>
        {body}
      </p>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--sp-3)",
          justifyContent: "flex-end",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          disabled={pending}
          data-testid={dataTestId ? `${dataTestId}-cancel` : "confirm-dialog-cancel"}
          style={cancelStyle}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={() => void handleConfirm()}
          disabled={pending}
          data-testid={dataTestId ? `${dataTestId}-confirm` : "confirm-dialog-confirm"}
          style={confirmStyle}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
