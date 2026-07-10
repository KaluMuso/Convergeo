"use client";

import { useTranslations } from "next-intl";

import { Button } from "../../listings/new/_lib/ui";
import { verifyErrorMessageKey } from "../_lib/verify-errors";

import type { VerifyErrorKind } from "../_lib/verify-errors";

export type VerifyResultState =
  | { kind: "idle" }
  | { kind: "verifying" }
  | { kind: "success"; orderId: string }
  | { kind: "error"; errorKind: VerifyErrorKind };

type VerifyResultProps = {
  state: VerifyResultState;
  onScanAnother: () => void;
  onRetry: () => void;
};

export function VerifyResult({ state, onScanAnother, onRetry }: VerifyResultProps) {
  const t = useTranslations("vendor");

  if (state.kind === "idle" || state.kind === "verifying") {
    return null;
  }

  if (state.kind === "success") {
    return (
      <div
        data-testid="scan-success"
        role="status"
        style={{
          borderRadius: "var(--r)",
          border: "1px solid var(--success)",
          background: "color-mix(in srgb, var(--success) 10%, var(--surface))",
          padding: "var(--sp-4)",
          textAlign: "center",
        }}
      >
        <p
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--fs-h3)",
            color: "var(--success)",
          }}
        >
          {t("scan.success.title")}
        </p>
        <p style={{ margin: "var(--sp-2) 0 var(--sp-4)", color: "var(--text-2)" }}>
          {t("scan.success.body", { orderId: state.orderId.slice(0, 8) })}
        </p>
        <Button
          type="button"
          loading={false}
          loadingLabel={t("scan.success.scanAnother")}
          onClick={onScanAnother}
        >
          {t("scan.success.scanAnother")}
        </Button>
      </div>
    );
  }

  const messageKey = verifyErrorMessageKey(state.errorKind);
  const isWrongQr = state.errorKind === "wrong_qr";

  return (
    <div
      data-testid={isWrongQr ? "scan-wrong-qr" : "scan-error"}
      role="alert"
      style={{
        borderRadius: "var(--r)",
        border: "1px solid var(--danger)",
        background: "color-mix(in srgb, var(--danger) 8%, var(--surface))",
        padding: "var(--sp-4)",
        textAlign: "center",
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--fs-h3)",
          color: "var(--danger)",
        }}
      >
        {t(`${messageKey}.title`)}
      </p>
      <p style={{ margin: "var(--sp-2) 0 var(--sp-4)", color: "var(--text-2)" }}>
        {t(`${messageKey}.body`)}
      </p>
      <Button
        type="button"
        variant="secondary"
        loading={false}
        loadingLabel={t("scan.errors.retry")}
        onClick={onRetry}
      >
        {t("scan.errors.retry")}
      </Button>
    </div>
  );
}
