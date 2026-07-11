"use client";

import { useTranslations } from "next-intl";

import { Button } from "../../../../listings/new/_lib/ui";

export type ScanResultKind =
  | "valid"
  | "queued"
  | "conflict"
  | "rejected"
  | "unknown_ticket"
  | "stale_window"
  | "not_synced"
  | "invalid_sig"
  | "invalid_format";

export type ScanResultState = { kind: "idle" } | { kind: ScanResultKind; ticketId: string | null };

const SUCCESS_KINDS = new Set<ScanResultKind>(["valid", "queued"]);

const MESSAGE_KEY_BY_KIND: Record<ScanResultKind, string> = {
  valid: "valid",
  queued: "queued",
  conflict: "conflict",
  rejected: "rejected",
  unknown_ticket: "unknownTicket",
  stale_window: "staleWindow",
  not_synced: "notSynced",
  invalid_sig: "invalidSig",
  invalid_format: "invalidFormat",
};

type ScanResultFlashProps = {
  state: ScanResultState;
  onDismiss: () => void;
};

export function ScanResultFlash({ state, onDismiss }: ScanResultFlashProps) {
  const t = useTranslations("vendor");

  if (state.kind === "idle") {
    return null;
  }

  const isSuccess = SUCCESS_KINDS.has(state.kind);
  const messageKey = `scan.eventCheckIn.result.${MESSAGE_KEY_BY_KIND[state.kind]}`;
  const tone = isSuccess ? "success" : "danger";

  return (
    <div
      data-testid={isSuccess ? "event-scan-flash-success" : "event-scan-flash-error"}
      role={isSuccess ? "status" : "alert"}
      style={{
        borderRadius: "var(--r)",
        border: `1px solid var(--${tone})`,
        background: `color-mix(in srgb, var(--${tone}) 10%, var(--surface))`,
        padding: "var(--sp-4)",
        textAlign: "center",
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--fs-h3)",
          color: `var(--${tone})`,
        }}
      >
        {t(`${messageKey}.title`)}
      </p>
      <p style={{ margin: "var(--sp-2) 0 var(--sp-4)", color: "var(--text-2)" }}>
        {t(`${messageKey}.body`, { ticketId: state.ticketId ? state.ticketId.slice(0, 8) : "" })}
      </p>
      <Button
        type="button"
        variant={isSuccess ? "primary" : "secondary"}
        loading={false}
        loadingLabel={t("scan.eventCheckIn.result.scanAnother")}
        onClick={onDismiss}
      >
        {t("scan.eventCheckIn.result.scanAnother")}
      </Button>
    </div>
  );
}
